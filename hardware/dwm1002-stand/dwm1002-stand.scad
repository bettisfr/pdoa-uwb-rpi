// Parametric desktop stand for the Decawave DWM1002 PDoA node.
// The PCB is vertical in the X/Z plane and slides into two open-top saddles.

$fn = 64;

pcb_width = 59;
pcb_height = 72;
clear_above_z = 45;

// Clearance between the front and rear saddle walls. This includes the PCB,
// connectors, solder joints, and component protrusions near the lower edge.
pcb_envelope = 4;

base_width = 70;
base_depth = 30;
base_thickness = 3;
base_corner_radius = 4;

saddle_floor = 3;
saddle_wall = 2;
join_overlap = 0.2;
right_stop_clearance = 0;
right_stop_height = 12;
right_stop_thickness = 2;

// Saddles are [start, end, height], with horizontal positions measured from
// the PCB left edge. Add, remove, or adjust entries to avoid components.
saddle_intervals = [
    [6, 15, 25],
    [20, 30, 30],
    [40, pcb_width, 30]
];

mount_hole_diameter = 4.5;  // M4 clearance
mount_hole_x = 28;
mount_hole_y = 10;
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

module stand() {
    base();
    for (interval = saddle_intervals)
        saddle(interval);
    right_stop();
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
