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
! mcregen_verify_ft_insts yes
! graphics win32_gdi
display shaded
regen_data_sharing_ref_models yes
enable_auto_regen yes


! =========================================================
! HEADLESS / AUTOMATION STABILITY
! Prevent interactive prompts and unstable UI behavior
! =========================================================

prompt_on_exit no
regen_failure_handling no_resolve_mode
allow_mfg_in_assem_mode yes

! graphics NO_GRAPHICS
! NOTE:
! Keep commented unless testing proves it is stable.
! Some raster/JPEG exports fail in NO_GRAPHICS mode.

! =========================================================
! FAMILY TABLE / RETRIEVAL STABILITY
! Critical for DBatch + FT instances
! =========================================================

retrieve_data_sharing_ref_parts yes

! =========================================================
! DRAWING / MODEL CLEANUP
! =========================================================

cleanup_drawing_dependencies yes

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

enable_opengl_fbo no

! =========================================================
! MODEL DISPLAY CLEANUP
! Hide datums, refs, quilts, etc.
! Keeps exported JPEGs clean
! =========================================================

display_planes no
display_axes no
display_points no
display_coord_sys no
display_annotations no
datum_display no

! =========================================================
! ASSEMBLY DISPLAY
! =========================================================

display_comps_to_assemble no
freeze_failed_assy_comp yes

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

display_dwg_tol_tags no

! =========================================================
! OPTIONAL STARTUP SETTINGS
! Leave commented unless needed
! =========================================================

! start_model_dir
! template_part 
! template_assembly 
! template_drawing
