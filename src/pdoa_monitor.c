#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/time.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_DEVICE "/dev/ttyACM0"
#define DEFAULT_TAG_CONFIG "config/tags.json"
#define MAX_PAYLOAD 4096
#define MAX_TAGS 64
#define TAG_STALE_SECONDS 5

static volatile sig_atomic_t keep_running = 1;

struct options {
    const char *device;
    const char *tag_config;
    bool raw;
    bool show_all_json;
    bool stream;
    const char *tag_aliases[MAX_TAGS];
    size_t tag_alias_count;
};

struct tag_entry {
    char a16[16];
    char a64[32];
};

struct tag_map {
    struct tag_entry entries[MAX_TAGS];
    size_t len;
};

struct twr_sample {
    char a16[16];
    int r;
    int t;
    int d;
    int p;
    int x;
    int y;
    int o;
};

struct tag_state {
    char a16[16];
    char label[32];
    struct twr_sample sample;
    time_t updated_at;
    bool active;
};

struct dashboard {
    struct tag_state tags[MAX_TAGS];
    size_t len;
    bool dirty;
};

static void on_signal(int signum)
{
    (void)signum;
    keep_running = 0;
}

static void usage(const char *argv0)
{
    fprintf(stderr,
            "Usage: %s [-d DEVICE] [-t A16=A64] [--raw] [--all]\n"
            "\n"
            "Options:\n"
            "  -d DEVICE  Serial device, default " DEFAULT_DEVICE "\n"
            "  -c FILE    Tag config JSON, default " DEFAULT_TAG_CONFIG "\n"
            "  -t A16=A64 Add a tag alias, can be repeated\n"
            "  --stream   Append every TWR sample instead of redrawing a stable table\n"
            "  --raw      Print raw JS payloads as well as parsed rows\n"
            "  --all      Print non-TWR JSON payloads\n",
            argv0);
}

static int parse_options(int argc, char **argv, struct options *opts)
{
    opts->device = DEFAULT_DEVICE;
    opts->tag_config = DEFAULT_TAG_CONFIG;
    opts->raw = false;
    opts->show_all_json = false;
    opts->stream = false;
    opts->tag_alias_count = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-d") == 0) {
            if (i + 1 >= argc) {
                usage(argv[0]);
                return -1;
            }
            opts->device = argv[++i];
        } else if (strcmp(argv[i], "-c") == 0) {
            if (i + 1 >= argc) {
                usage(argv[0]);
                return -1;
            }
            opts->tag_config = argv[++i];
        } else if (strcmp(argv[i], "-t") == 0) {
            if (i + 1 >= argc || opts->tag_alias_count >= MAX_TAGS) {
                usage(argv[0]);
                return -1;
            }
            opts->tag_aliases[opts->tag_alias_count++] = argv[++i];
        } else if (strcmp(argv[i], "--stream") == 0) {
            opts->stream = true;
        } else if (strcmp(argv[i], "--raw") == 0) {
            opts->raw = true;
        } else if (strcmp(argv[i], "--all") == 0) {
            opts->show_all_json = true;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            usage(argv[0]);
            exit(0);
        } else {
            usage(argv[0]);
            return -1;
        }
    }

    return 0;
}

static void trim_string(char *s)
{
    char *start = s;
    while (isspace((unsigned char)*start)) {
        start++;
    }
    if (start != s) {
        memmove(s, start, strlen(start) + 1);
    }

    size_t len = strlen(s);
    while (len > 0 && isspace((unsigned char)s[len - 1])) {
        s[--len] = '\0';
    }
}

static int hex_value(int c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return 10 + c - 'a';
    }
    if (c >= 'A' && c <= 'F') {
        return 10 + c - 'A';
    }
    return -1;
}

static int parse_hex4(const unsigned char *s)
{
    int value = 0;
    for (int i = 0; i < 4; i++) {
        int nibble = hex_value(s[i]);
        if (nibble < 0) {
            return -1;
        }
        value = (value << 4) | nibble;
    }
    return value;
}

static int open_serial(const char *device)
{
    int fd = open(device, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        perror(device);
        return -1;
    }

    struct termios tio;
    if (tcgetattr(fd, &tio) != 0) {
        perror("tcgetattr");
        close(fd);
        return -1;
    }

    cfmakeraw(&tio);
    cfsetispeed(&tio, B115200);
    cfsetospeed(&tio, B115200);
    tio.c_cflag |= (CLOCAL | CREAD);
#ifdef CRTSCTS
    tio.c_cflag &= ~CRTSCTS;
#endif
    tio.c_cc[VMIN] = 0;
    tio.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tio) != 0) {
        perror("tcsetattr");
        close(fd);
        return -1;
    }

    return fd;
}

static bool json_string_field(const char *json, const char *key, char *out, size_t out_size)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\":\"", key);

    const char *start = strstr(json, pattern);
    if (!start) {
        return false;
    }
    start += strlen(pattern);

    const char *end = strchr(start, '"');
    if (!end) {
        return false;
    }

    size_t len = (size_t)(end - start);
    if (len >= out_size) {
        len = out_size - 1;
    }
    memcpy(out, start, len);
    out[len] = '\0';
    return true;
}

static bool json_int_field(const char *json, const char *key, int *out)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);

    const char *start = strstr(json, pattern);
    if (!start) {
        return false;
    }
    start += strlen(pattern);

    while (*start == ' ') {
        start++;
    }

    char *end = NULL;
    long value = strtol(start, &end, 10);
    if (end == start) {
        return false;
    }

    *out = (int)value;
    return true;
}

static const char *find_string_after(const char *start, const char *key, char *out, size_t out_size)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\":\"", key);

    const char *field = strstr(start, pattern);
    if (!field) {
        return NULL;
    }

    field += strlen(pattern);
    const char *end = strchr(field, '"');
    if (!end) {
        return NULL;
    }

    size_t len = (size_t)(end - field);
    if (len >= out_size) {
        len = out_size - 1;
    }
    memcpy(out, field, len);
    out[len] = '\0';
    return end + 1;
}

static const char *find_json_string_in_object(const char *object_start, const char *object_end,
                                              const char *key, char *out, size_t out_size)
{
    char pattern[64];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);

    const char *field = object_start;
    while ((field = strstr(field, pattern)) != NULL && field < object_end) {
        const char *p = field + strlen(pattern);
        while (p < object_end && isspace((unsigned char)*p)) {
            p++;
        }
        if (p >= object_end || *p != ':') {
            field++;
            continue;
        }
        p++;
        while (p < object_end && isspace((unsigned char)*p)) {
            p++;
        }
        if (p >= object_end || *p != '"') {
            field++;
            continue;
        }
        p++;

        const char *end = p;
        while (end < object_end && *end != '"') {
            end++;
        }
        if (end >= object_end) {
            return NULL;
        }

        size_t len = (size_t)(end - p);
        if (len >= out_size) {
            len = out_size - 1;
        }
        memcpy(out, p, len);
        out[len] = '\0';
        return end + 1;
    }

    return NULL;
}

static void tag_map_put(struct tag_map *map, const char *a16, const char *a64, bool overwrite)
{
    if (a16[0] == '\0' || a64[0] == '\0') {
        return;
    }

    for (size_t i = 0; i < map->len; i++) {
        if (strcmp(map->entries[i].a16, a16) == 0) {
            if (overwrite) {
                snprintf(map->entries[i].a64, sizeof(map->entries[i].a64), "%s", a64);
            }
            return;
        }
    }

    if (map->len >= MAX_TAGS) {
        return;
    }

    snprintf(map->entries[map->len].a16, sizeof(map->entries[map->len].a16), "%s", a16);
    snprintf(map->entries[map->len].a64, sizeof(map->entries[map->len].a64), "%s", a64);
    map->len++;
}

static void load_config_tags(struct tag_map *map, const char *path)
{
    FILE *fp = fopen(path, "rb");
    if (!fp) {
        if (errno != ENOENT) {
            perror(path);
        }
        return;
    }

    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return;
    }
    long size = ftell(fp);
    if (size <= 0 || size > 1024 * 1024) {
        fclose(fp);
        return;
    }
    rewind(fp);

    char *json = malloc((size_t)size + 1);
    if (!json) {
        fclose(fp);
        return;
    }

    size_t nread = fread(json, 1, (size_t)size, fp);
    fclose(fp);
    json[nread] = '\0';

    const char *cursor = json;
    while ((cursor = strchr(cursor, '{')) != NULL) {
        const char *end = strchr(cursor, '}');
        if (!end) {
            break;
        }

        char a16[16] = "";
        char id[32] = "";
        char name[32] = "";

        find_json_string_in_object(cursor, end, "a16", a16, sizeof(a16));
        find_json_string_in_object(cursor, end, "id", id, sizeof(id));
        find_json_string_in_object(cursor, end, "name", name, sizeof(name));

        trim_string(a16);
        trim_string(id);
        trim_string(name);

        if (a16[0] && id[0]) {
            tag_map_put(map, a16, name[0] ? name : id, true);
            tag_map_put(map, id, name[0] ? name : id, true);
        }

        cursor = end + 1;
    }

    free(json);
}

static void load_aliases(struct tag_map *map, const struct options *opts)
{
    for (size_t i = 0; i < opts->tag_alias_count; i++) {
        char alias[96];
        snprintf(alias, sizeof(alias), "%s", opts->tag_aliases[i]);

        char *sep = strchr(alias, '=');
        if (!sep) {
            fprintf(stderr, "Invalid tag alias: %s\n", opts->tag_aliases[i]);
            continue;
        }

        *sep = '\0';
        char *a16 = alias;
        char *a64 = sep + 1;
        trim_string(a16);
        trim_string(a64);
        tag_map_put(map, a16, a64, true);
    }
}

static const char *tag_map_lookup(const struct tag_map *map, const char *a16)
{
    for (size_t i = 0; i < map->len; i++) {
        if (strcmp(map->entries[i].a16, a16) == 0) {
            return map->entries[i].a64;
        }
    }
    return a16;
}

static void update_tag_map_from_payload(struct tag_map *map, const char *payload)
{
    const char *cursor = payload;

    while ((cursor = strstr(cursor, "\"a64\":\"")) != NULL) {
        char a64[32] = "";
        char a16[16] = "";

        const char *after_a64 = find_string_after(cursor, "a64", a64, sizeof(a64));
        if (!after_a64) {
            break;
        }

        const char *after_a16 = find_string_after(after_a64, "a16", a16, sizeof(a16));
        if (after_a16) {
            tag_map_put(map, a16, a64, false);
            cursor = after_a16;
        } else {
            cursor = after_a64;
        }
    }
}

static const char *now_hms(void)
{
    static char buf[16];
    time_t t = time(NULL);
    struct tm tm_value;

    localtime_r(&t, &tm_value);
    strftime(buf, sizeof(buf), "%H:%M:%S", &tm_value);
    return buf;
}

static long long now_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (long long)tv.tv_sec * 1000LL + tv.tv_usec / 1000LL;
}

static void print_header(void)
{
    printf("%-8s %-16s %6s %8s %8s %7s %7s %8s %8s\n",
           "age", "tag", "seq", "range_cm", "pdoa_deg", "x_cm", "y_cm", "clk_ppm", "t_us");
    fflush(stdout);
}

static bool parse_twr_sample(const char *payload, struct twr_sample *sample)
{
    if (!strstr(payload, "\"TWR\"")) {
        return false;
    }

    memset(sample, 0, sizeof(*sample));
    if (!json_string_field(payload, "a16", sample->a16, sizeof(sample->a16))) {
        return false;
    }

    json_int_field(payload, "R", &sample->r);
    json_int_field(payload, "T", &sample->t);
    json_int_field(payload, "D", &sample->d);
    json_int_field(payload, "P", &sample->p);
    json_int_field(payload, "Xcm", &sample->x);
    json_int_field(payload, "Ycm", &sample->y);
    json_int_field(payload, "O", &sample->o);
    return true;
}

static void dashboard_update(struct dashboard *dashboard, const struct tag_map *map, const struct twr_sample *sample)
{
    const char *label = tag_map_lookup(map, sample->a16);

    for (size_t i = 0; i < dashboard->len; i++) {
        if (strcmp(dashboard->tags[i].label, label) == 0) {
            snprintf(dashboard->tags[i].a16, sizeof(dashboard->tags[i].a16), "%s", sample->a16);
            dashboard->tags[i].sample = *sample;
            dashboard->tags[i].updated_at = time(NULL);
            dashboard->tags[i].active = true;
            dashboard->dirty = true;
            return;
        }
    }

    if (dashboard->len >= MAX_TAGS) {
        return;
    }

    struct tag_state *state = &dashboard->tags[dashboard->len++];
    snprintf(state->a16, sizeof(state->a16), "%s", sample->a16);
    snprintf(state->label, sizeof(state->label), "%s", label);
    state->sample = *sample;
    state->updated_at = time(NULL);
    state->active = true;
    dashboard->dirty = true;
}

static void dashboard_render(struct dashboard *dashboard)
{
    if (!dashboard->dirty) {
        time_t now = time(NULL);
        for (size_t i = 0; i < dashboard->len; i++) {
            if (now - dashboard->tags[i].updated_at > TAG_STALE_SECONDS) {
                dashboard->dirty = true;
                break;
            }
        }
        if (!dashboard->dirty) {
            return;
        }
    }

    time_t now = time(NULL);

    for (size_t i = 0; i < dashboard->len;) {
        if (now - dashboard->tags[i].updated_at > TAG_STALE_SECONDS) {
            memmove(&dashboard->tags[i], &dashboard->tags[i + 1],
                    (dashboard->len - i - 1) * sizeof(dashboard->tags[i]));
            dashboard->len--;
        } else {
            i++;
        }
    }

    printf("\033[H\033[J");
    printf("PDoA monitor - %zu active tag%s - %s\n",
           dashboard->len, dashboard->len == 1 ? "" : "s", now_hms());
    print_header();

    for (size_t i = 0; i < dashboard->len; i++) {
        const struct tag_state *state = &dashboard->tags[i];
        const struct twr_sample *s = &state->sample;
        long age = (long)(now - state->updated_at);
        char age_label[16];
        snprintf(age_label, sizeof(age_label), "%lds", age);

        printf("%-8s %-16s %6d %8d %8d %7d %7d %8.2f %8d\n",
               age_label, state->label, s->r, s->d, s->p, s->x, s->y, s->o / 100.0, s->t);
    }

    fflush(stdout);
    dashboard->dirty = false;
}

static void write_command(int fd, const char *command)
{
    size_t len = strlen(command);
    size_t done = 0;

    while (done < len) {
        ssize_t n = write(fd, command + done, len - done);
        if (n > 0) {
            done += (size_t)n;
        } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
            usleep(10000);
        } else if (n < 0) {
            perror("write");
            return;
        }
    }
}

static void handle_payload(const char *payload, const struct options *opts, struct tag_map *map,
                           struct dashboard *dashboard)
{
    update_tag_map_from_payload(map, payload);

    if (opts->raw) {
        printf("RAW %s\n", payload);
    }

    struct twr_sample sample;
    if (parse_twr_sample(payload, &sample)) {
        if (opts->stream) {
            const char *tag_label = tag_map_lookup(map, sample.a16);
            printf("%-8s %-16s %6d %8d %8d %7d %7d %8.2f %8d\n",
                   now_hms(), tag_label, sample.r, sample.d, sample.p,
                   sample.x, sample.y, sample.o / 100.0, sample.t);
        } else {
            dashboard_update(dashboard, map, &sample);
        }
    } else if (strstr(payload, "\"NewTag\"")) {
        char tag[32] = "-";
        json_string_field(payload, "NewTag", tag, sizeof(tag));
        if (opts->stream || opts->show_all_json) {
            printf("%-8s new tag discovered: %s\n", now_hms(), tag);
        }
    } else if (opts->show_all_json) {
        printf("%-8s %s\n", now_hms(), payload);
    }

    fflush(stdout);
}

static void process_stream(unsigned char *buf, size_t *len, const struct options *opts, struct tag_map *map,
                           struct dashboard *dashboard)
{
    size_t pos = 0;

    while (*len - pos >= 6) {
        if (buf[pos] != 'J' || buf[pos + 1] != 'S') {
            pos++;
            continue;
        }

        int payload_len = parse_hex4(&buf[pos + 2]);
        if (payload_len < 0 || payload_len > MAX_PAYLOAD) {
            pos++;
            continue;
        }

        size_t frame_len = 6 + (size_t)payload_len;
        if (*len - pos < frame_len) {
            break;
        }

        char payload[MAX_PAYLOAD + 1];
        memcpy(payload, &buf[pos + 6], (size_t)payload_len);
        payload[payload_len] = '\0';
        handle_payload(payload, opts, map, dashboard);

        pos += frame_len;
    }

    if (pos > 0) {
        memmove(buf, buf + pos, *len - pos);
        *len -= pos;
    }
}

int main(int argc, char **argv)
{
    struct options opts;
    if (parse_options(argc, argv, &opts) != 0) {
        return 2;
    }

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);

    int fd = open_serial(opts.device);
    if (fd < 0) {
        return 1;
    }

    if (opts.stream) {
        printf("Listening on %s. Press Ctrl-C to stop.\n", opts.device);
        print_header();
    } else {
        printf("\033[?25l");
        fflush(stdout);
    }

    unsigned char buf[MAX_PAYLOAD * 2];
    size_t len = 0;
    struct tag_map map = {0};
    struct dashboard dashboard = {0};
    load_config_tags(&map, opts.tag_config);
    load_aliases(&map, &opts);
    long long last_render_ms = 0;

    write_command(fd, "GETKLIST\r");
    usleep(100000);
    write_command(fd, "GETKLIST\r");

    while (keep_running) {
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(fd, &readfds);

        struct timeval timeout;
        timeout.tv_sec = 0;
        timeout.tv_usec = 250000;

        int rc = select(fd + 1, &readfds, NULL, NULL, &timeout);
        if (rc < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("select");
            break;
        }

        if (rc > 0 && FD_ISSET(fd, &readfds)) {
            ssize_t n = read(fd, buf + len, sizeof(buf) - len);
            if (n > 0) {
                len += (size_t)n;
                process_stream(buf, &len, &opts, &map, &dashboard);
                if (len == sizeof(buf)) {
                    len = 0;
                }
            } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                perror("read");
                break;
            }
        }

        long long current_ms = now_ms();
        if (!opts.stream && current_ms - last_render_ms >= 250) {
            dashboard_render(&dashboard);
            last_render_ms = current_ms;
        }
    }

    close(fd);
    if (!opts.stream) {
        printf("\033[?25h");
    }
    printf("\nStopped.\n");
    return 0;
}
