// Parametric desktop stand for the Decawave DWM1002 PDoA node.
// The PCB is vertical in the X/Z plane and slides into two open-top saddles.

$fn = 64;

pcb_width = 60;
pcb_height = 72;
clear_above_z = 45;

// Clearance between the front and rear saddle walls. This includes the PCB,
// connectors, solder joints, and component protrusions near the lower edge.
pcb_envelope = 4;

base_width = 80;
base_depth = 50;
base_thickness = 3;
base_corner_radius = 4;

saddle_floor = 3;
saddle_wall = 2;
join_overlap = 0.2;
right_stop_clearance = 0;
right_stop_height = 12;
right_stop_thickness = 2;
left_stop_bottom = 15;
left_stop_thickness = 2;

// Saddles are [start, end, height], with horizontal positions measured from
// the PCB left edge. Add, remove, or adjust entries to avoid components.
saddle_intervals = [
    [6, 15, 25],
    [20, 30, 30],
    [40, pcb_width, 30]
];

mount_hole_diameter = 4.5;  // M4 clearance
mount_hole_x = 33;
mount_hole_y = 18;
countersink_diameter = 8.5;
countersink_depth = 1.5;

show_board_preview = true;

for (interval = saddle_intervals) {
    assert(interval[0] >= 0 && interval[1] <= pcb_width,
           "Every saddle interval must fit within the PCB width.");
    assert(interval[1] > interval[0],
           "Every saddle interval must have a positive width.");
    assert(interval[2] <= clear_above_z,
           "Every saddle must remain below the exposed-board height.");
}

module rounded_box_2d(width, depth, radius) {
    hull() {
        for (x = [-width / 2 + radius, width / 2 - radius])
            for (y = [-depth / 2 + radius, depth / 2 - radius])
                translate([x, y]) circle(r = radius);
    }
}

module base() {
    difference() {
        linear_extrude(base_thickness)
            rounded_box_2d(base_width, base_depth, base_corner_radius);

        for (x = [-mount_hole_x, mount_hole_x])
            for (y = [-mount_hole_y, mount_hole_y]) {
                translate([x, y, -0.1])
                    cylinder(h = base_thickness + 0.2, d = mount_hole_diameter);
                translate([x, y, base_thickness - countersink_depth])
                    cylinder(h = countersink_depth + 0.1,
                             d1 = mount_hole_diameter,
                             d2 = countersink_diameter);
            }
    }
}

module saddle(interval) {
    saddle_width = interval[1] - interval[0];
    saddle_height = interval[2];
    x_position = -pcb_width / 2 + interval[0] + saddle_width / 2;
    outer_depth = pcb_envelope + 2 * saddle_wall;

    translate([x_position, 0, base_thickness - join_overlap])
        difference() {
            translate([-saddle_width / 2, -outer_depth / 2, 0])
                cube([saddle_width, outer_depth, saddle_height + join_overlap]);

            // The slot stops above the base, creating a seat for the PCB.
            translate([-saddle_width / 2 - 0.1,
                       -pcb_envelope / 2,
                       saddle_floor + join_overlap])
                cube([saddle_width + 0.2,
                      pcb_envelope,
                      saddle_height - saddle_floor + 0.1]);
        }
}

module right_stop() {
    outer_depth = pcb_envelope + 2 * saddle_wall;

    translate([pcb_width / 2 + right_stop_clearance,
               -outer_depth / 2,
               base_thickness - join_overlap])
        cube([right_stop_thickness,
              outer_depth,
              right_stop_height + join_overlap]);
}

module raised_left_stop() {
    outer_depth = pcb_envelope + 2 * saddle_wall;
    first_saddle_start = -pcb_width / 2 + saddle_intervals[0][0];
    first_saddle_height = saddle_intervals[0][2];
    board_left = -pcb_width / 2;
    stop_height = first_saddle_height - left_stop_bottom;
    bridge_width = first_saddle_start - board_left + left_stop_thickness;

    assert(left_stop_bottom > 13,
           "The raised left stop must remain above the USB-C connector.");
    assert(stop_height > 0,
           "The raised left stop must end below the first saddle height.");

    // Side datum at the PCB edge, above the USB-C connector.
    translate([board_left - left_stop_thickness,
               -outer_depth / 2,
               base_thickness + left_stop_bottom])
        cube([left_stop_thickness, outer_depth, stop_height]);

    // Front and rear bridges connect the datum to the first saddle while
    // preserving the same component envelope as the saddle slot.
    for (y = [-outer_depth / 2, pcb_envelope / 2])
        translate([board_left - left_stop_thickness,
                   y,
                   base_thickness + left_stop_bottom])
            cube([bridge_width, saddle_wall, stop_height]);

    // Two 45-degree gussets support the raised bridges without filling the
    // central USB-C cable corridor or requiring slicer-generated supports.
    gusset_run = first_saddle_start - (board_left - left_stop_thickness);
    gusset_top = base_thickness + left_stop_bottom;
    gusset_bottom = gusset_top - gusset_run;

    for (y = [-outer_depth / 2, pcb_envelope / 2])
        polyhedron(
            points = [
                [board_left - left_stop_thickness, y, gusset_top],
                [first_saddle_start, y, gusset_top],
                [first_saddle_start, y, gusset_bottom],
                [board_left - left_stop_thickness, y + saddle_wall, gusset_top],
                [first_saddle_start, y + saddle_wall, gusset_top],
                [first_saddle_start, y + saddle_wall, gusset_bottom]
            ],
            faces = [
                [0, 2, 1], [3, 4, 5],
                [0, 1, 4, 3], [1, 2, 5, 4], [2, 0, 3, 5]
            ],
            convexity = 4
        );
}

module stand() {
    base();
    for (interval = saddle_intervals)
        saddle(interval);
    right_stop();
    raised_left_stop();
}

module board_preview() {
    preview_thickness = 1;
    color([0.08, 0.45, 0.22, 0.45])
        translate([-pcb_width / 2,
                   -preview_thickness / 2,
                   base_thickness + saddle_floor])
            cube([pcb_width, preview_thickness, pcb_height]);

    // Marks the height above which the board must be completely exposed.
    color([0.9, 0.15, 0.1, 0.65])
        translate([-pcb_width / 2 - 2,
                   -preview_thickness,
                   base_thickness + saddle_floor + clear_above_z])
            cube([pcb_width + 4, preview_thickness * 2, 0.8]);
}

stand();

if ($preview && show_board_preview)
    board_preview();
