! =========================================================
! Creo Distributed Batch / ModelCHECK / JPEG Export Config
! Purpose:
!   - Stable headless DBatch execution
!   - Family table reliability
!   - Clean 3D JPEG exports
!   - Clean 2D drawing JPEG exports
!   - Shared config for ModelCHECK + exports
! =========================================================

! =========================================================
! MODEL CHECK
! =========================================================

modelcheck_enabled yes

! =========================================================
! HEADLESS / AUTOMATION STABILITY
! Prevent interactive prompts and unstable UI behavior
! =========================================================

prompt_on_exit no
confirm_on_delete no
regen_failure_handling no_resolve_mode

! graphics NO_GRAPHICS
! NOTE:
! Keep commented unless testing proves it is stable.
! Some raster/JPEG exports fail in NO_GRAPHICS mode.

! =========================================================
! FAMILY TABLE / RETRIEVAL STABILITY
! Critical for DBatch + FT instances
! =========================================================

retrieve_data_sharing_ref_parts yes
dm_family_table_inst_name yes
instance_dep_generic yes
display_out_of_date_instances no

! =========================================================
! DRAWING / MODEL CLEANUP
! =========================================================

cleanup_drawing_dependencies yes
save_display no

! =========================================================
! PERFORMANCE / DISPLAY QUALITY
! Lower values improve DBatch throughput
! =========================================================

shade_quality 3
interface_quality 3
edge_display_quality low

! =========================================================
! DISPLAY STYLE
! Force consistent shaded output
! =========================================================

display_style shade
shade_with_edges yes
shade_with_reflections no
shade_with_materials no
enable_transparency no
enable_opengl_fbo no
hlr_for_quilt no
display_filled_patterns yes

! =========================================================
! MODEL DISPLAY CLEANUP
! Hide datums, refs, quilts, etc.
! Keeps exported JPEGs clean
! =========================================================

display_planes no
display_axes no
display_points no
display_coord_sys no
display_quilts no
display_annotations no
datum_display no
show_axes no
show_planes no
show_quilts no
show_coord_sys no
show_points no
intf3d_out_datums no

! =========================================================
! ASSEMBLY DISPLAY
! =========================================================

display_comps_to_assemble no

! =========================================================
! VIEW / SPIN / INTERACTION
! =========================================================

spin_with_part_entities no

! display no_hidden
! Optional:
! Some Creo versions produce odd raster results with this.

! =========================================================
! DRAWING DISPLAY CLEANUP
! Removes annotation clutter from 2D JPEG exports
! =========================================================

display_notes no
display_gtols no
display_tol no
display_sketch_dimensions no
display_dwg_tol_tags no

! =========================================================
! OPTIONAL STARTUP SETTINGS
! Leave commented unless needed
! =========================================================

! start_model_dir
! template_part
! template_assembly
! template_drawing
