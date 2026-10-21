const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const linkage = b.option(std.builtin.LinkMode, "linkage", "Link mode: dynamic (default for host) or static (for the freestanding targets)") orelse .dynamic;

    const lib_mod = b.createModule(.{
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });

    const lib = b.addLibrary(.{
        .name = "lwc_zig",
        .linkage = linkage,
        .root_module = lib_mod,
    });

    if (linkage == .static) {
        lib.bundle_compiler_rt = false;
    }

    b.installArtifact(lib);
}
