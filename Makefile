CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -O2
CPPFLAGS ?=
LDFLAGS ?=

BIN := pdoa-monitor
SRC := src/pdoa_monitor.c
WEB_HOST ?= 0.0.0.0
WEB_PORT ?= 8080
WEB_DEVICE ?= /dev/ttyACM0
STDDEV_WINDOW ?= 100

.PHONY: all clean run web

all: $(BIN)

$(BIN): $(SRC)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< $(LDFLAGS)

run: $(BIN)
	./$(BIN)

web: $(BIN)
	./scripts/pdoa-web.py --host $(WEB_HOST) --port $(WEB_PORT) --device $(WEB_DEVICE) --stddev-window $(STDDEV_WINDOW)

clean:
	rm -f $(BIN)
