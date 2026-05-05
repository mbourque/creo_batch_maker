! Configuration file for ModelCHECK. 
! Date: 04/17/2001 (2001 default)
! Date: 06/20/2001 (SS-added NOTE_CASE, LAYER_DTM_BLANK for 2002-simple)
! Date: 07/03/2001 (VA-added EXTERNAL_REFS for 2002-simple)
!                  (RJ added LAYER_EXT_ITEMS)
!                  (SS added VIEW_SCALE for 2002) 
!                  (VA-added CIRCULAR_REFS for 2002-simple)
!                  (VA-added DEPENDENT_FEATURE for 2002-simple)
! Date: 06/Aug/2001 (SS Changes to FAMILY_VERIFY for 2002)
! Date: 03/Aug/2001 (AMN added YNEW for IMPORT_FEAT)
! Date: 18/Aug/2001 (AMN added DESIGNATED_ATTR)
! Date: 25/Sep/2001 (Remove EXT_REF_INFO)
! Date: 19/Feb/2002 (refs to EXTERNAL_DEPS)
! Date: 02/May/2002 (Defaults for Pro/E 2002 alpha release)
! Date: 30/July/2002 (RJ: Corrected spell for SMALL_CYLSRF)
! Date: 13/Mar/2003 (RJ: Added CHILDREN_EXIST)
! 06-Feb-07 L-01-26 $$1 vmishra removed DRAWING_GTOLS.
! 15-Oct-13 P-20-41 $$2 ngarad  Added assembly component checks.
! 30-Sep-19 P-70-30 $$3 prmore  SPR:7258438: removed ABS_ACCURACY,REGEN_WARN.
! 25-Apr-22 Q-10-16 $$4 ksingh  Marked Matrics colum as Y by default.
!
! E     Check the item.  If not succeed, report as an error
! W     Check the item.  If not succeed, report as a warning
! N     Do not check the item.
! Y     Check the item.  If not succeed, do not report err or warn
!
! "I" = Interactive
! "B" = Batch
! "R" = Regeneration
! "S" = Save

! ----------------------------------------------------------------
#            Options           "I"     "B"     "R"     "S"     "M"
! ----------------------------------------------------------------

! ----------------------------------------------------------------
# Options                   (Y/N/E/W)        (N/E/W)
#                                   (Y/N/E/W)        (N/E/W)
! ----------------------------------------------------------------

# PART REPORT CONFIGURATION 
#CHK_CUSTOM1_PRT      YNEW      E       E       E       E       Y 

ACCURACY_INFO        YNEW       W       W       W       W       Y
ADD_CHK_PARAM        YN         N       N       N       N       Y
BURIED_FEAT          YNEW       E       E       E       E       Y
CHAMFER_CHILD        YNEW       E       E       E       E       Y
CHILDREN_EXIST       YNEW       E       E       E       E       Y
COSMETIC_FEAT        YNEW       Y       Y       N       N       Y
CYL_CUT_SLOTS        YNEW       N       N       N       N       Y
CYL_DIAMS            YNEW       N       N       N       N       Y
DATUM_RENAME         YNEW       N       N       N       N       Y
DEF_DENSITY          YNEW       N       N       N       N       Y
DEFAULT_CHILD        YN         Y       Y       N       N       Y
DRAFT_ANGLES         YNEW       N       N       N       N       Y
DRAFT_CHILD          YNEW       W       W       W       W       Y
DTM_AXES_INFO        YN         Y       Y       N       N       Y
DTM_CSYS_INFO        YN         Y       Y       N       N       Y
DTM_CURVE_INFO       YN         Y       Y       N       N       Y
DTM_PLANE_INFO       YN         Y       Y       N       N       Y
DTM_POINT_INFO       YN         Y       Y       N       N       Y
DUPLICATE_MODELS     YNEW       N       N       N       N       Y
EARLY_CHAMFER        YNEW       N       N       N       N       Y
EARLY_COSMETIC       YNEW       N       N       N       N       Y
EARLY_DRAFT          YNEW       N       N       N       N       Y
EARLY_ROUND          EENN       N       N       N       N       Y
EDGE_REFERENCES      YNEW       E       E       E       E       Y
EXTRA_LAYERS         YNEW       N       N       N       N       Y
EXTRA_PARAMS         YNEW       N       N       N       N       Y
FAMILY_INFO          YNEW       W       W       W       W       Y
FEATURE_INFO         YN         Y       Y       N       N       Y
FILE_SIZE            YN         Y       Y       N       N       Y
FREEFORM             YN         Y       Y       N       N       Y
FT_DEF_VALS          YNEW       N       N       N       N       Y
FT_STD_PARMS         YNEW       N       N       N       N       Y
GEOM_CHECKS          YNEW       E       E       N       E       Y
GEOMETRIC_TOL        YN         Y       Y       N       N       Y
HOLE_DIAMS           YNEW       N       N       N       N       Y
IGNORE_FEAT          YN         Y       Y       N       Y       Y
IMPORT_FEAT          YNEW       Y       Y       N       N       Y
INCOMPLETE_FEAT      YNEW       E       W       N       N       Y
INSERT_MODE          YNEW       E       W       N       N       Y
INSTANCE_NAME        YNEW       N       N       N       N       Y
LAYER_DISPSTAT       YNEW       W       W       W       W       Y
LAYER_DTM_BLANK      YNEW       W       W       W       W       Y
LAYER_EXT_ITEMS      YNEW       W       W       W       W       Y
LAYER_INFO           YN         Y       Y       N       N       Y 
LAYER_MOVE           YNEW       W       Y       N       N       Y
LAYER_PLACE          YNEW       W       W       W       W       Y
LAYER_STATUS         YNEW       W       W       W       W       Y
LAYOUT_INFO          YN         Y       Y       N       N       Y
LOW_TOLERANCE        YNEW       Y       Y       N       N       Y
MATERIAL_INFO        YNEW       N       N       N       N       Y
MEMORY_SPACE         YN         Y       Y       N       N       Y
MERGE_FEAT           YNEW       N       N       N       N       Y
MINMAXTOL_INFO       YN         Y       Y       N       N       Y
MODEL_NAME           YNEW       E       E       N       W       Y
MODEL_NAME_STR       YN         Y       Y       N       N       Y
NAMED_FEAT           YN         Y       Y       N       N       Y
OVERALL_SIZE         YN         Y       Y       N       N       Y
PARAM_INFO           YN         Y       Y       N       N       Y
PARAM_NOTE_REQ       YNEW       N       N       N       N       Y
PARAM_NOTE_UNACC     YNEW       N       N       N       N       Y
PARAM_RENAME         YNEW       N       N       N       N       Y
PARAM_SPELL          YNEW       N       N       N       N       Y
PARAM_UNUSED         YNEW       N       N       N       N       Y
PARAMCHECK           YNEW       E       E       N       W       Y
PLANE_CHILD          YNEW       N       N       N       N       Y
PLANE_PARENT         YNEW       E       Y       N       N       Y
PRO_VERSION          YNEW       N       N       N       N       Y
RC_INCOMPLETED       YNEW       N       N       N       N       Y
REG_FEATURES         YN         Y       Y       N       N       Y
REGEN_ERRS           YNEW       E       N       N       N       Y

REGEN_WRNS           YNEW       W       N       N       N       Y
RELATION_COMM        YNEW       N       N       N       N       Y
RELATION_ERRS        YNEW       W       E       N       N       Y
RELATION_INFO        YN         Y       Y       N       N       Y
RELATION_MISS        YNEW       N       N       N       N       Y
RELATION_MULT        YNEW       W       W       W       W       Y
RENAMED_SYMBOLS      YN         N       N       N       N       Y
REPT_LAYR_ALWAYS	 YN		    Y	    Y	    Y	    Y       Y
ROUND_CHILD          YNEW       E       E       E       E       Y
RULECHECK_INFO       YN         N       N       N       N       Y
SHARP_EDGES          YNEW       N       N       N       N       Y
SHORT_EDGES          YNEW       E       E       N       E       Y
SHTMTL_BENDTAB       YNEW       N       N       N       N       Y
SHTMTL_FLAT          YNEW       N       N       N       N       Y
SHTMTL_THICK         YNEW       N       N       N       N       Y
SHTMTL_UNBENDS       YNEW       E       E       N       E       Y
SHTMTL_YFACTOR       YN         Y       Y       N       N       Y
SIMPREP_INFO         YN         Y       Y       N       N       Y
SIMPREP_NAME         YNEW       N       N       N       N       Y
SKETCH_ITEMS         YNEW       W       N       N       N       Y
SLA_INFO             YNEW       N       N       N       N       Y
SMALL_CYLSRF         YNEW       E       E       N       W       Y
SRF_EDGES            YNEW       N       N       N       N       Y
STARTCHECK           YNEW       E       E       N       W       Y 
SUP_FEATURES         YNEW       N       W       N       W       Y
UDF_INFO             YN         Y       Y       N       N       Y
UNITS_LENGTH         YNEW       Y       Y       N       N       Y
UNITS_MASS           YNEW       Y       Y       N       N       Y
VIEW_INFO            YN         Y       Y       N       N       Y
XSEC_INFO            YN         Y       Y       N       N       Y
EXTERNAL_DEPS        YNEW       W       W       N       N       Y
DEPENDENT_FEATURE    YNEW       N       N       N       N       Y
DESIGNATED_ATTR      YNEW       N       N       N       N       Y

# DRAWING REPORT CONFIGURATION
#STD_SYMBOLS         YNEW       E       E       N       E       Y
BOUND_INFO           YNEW       E       E       N       E       Y
DIM_OVERWRITE        YNEW       E       E       N       E       Y
DRAFT_GEOM           YNEW       E       E       N       E       Y
DRAWING_LAYERS       YNEW       E       E       N       E       Y
DRAWING_PARAMS       YNEW       E       E       N       E       Y
DRAWING_NAME         YNEW       W       W       N       W       Y
DEFAULT_VIEWS        YNEW       W       W       N       W       Y
ERASED_VIEWS         YNEW       W       W       N       W       Y
FORMAT_NAME          YNEW       N       N       N       N       Y
IGNORE_SHEETS        YN         N       N       N       N       Y
MODELS_USED          YN         Y       Y       Y       N       Y
NOTE_CASE            YNEW       N       N       N       N       Y
NOTE_FONT            YNEW       N       N       N       N       Y
NOTE_HEIGHT          YNEW       N       N       N       N       Y
NOTE_INFO            YN         Y       Y       N       N       Y
NOTE_SPELL           YNEW       E       E       N       E       Y
TITLE_SPELL          YNEW       E       E       N       E       Y
SYMBOL_SPELL         YNEW       N       N       N       N       Y
NOTE_UNACCEPT        YNEW       N       N       N       N       Y
NUM_DRAW_SHEETS      YNEW       N       N       N       N       Y
OVERLAP_INFO         YNEW       E       E       N       E       Y
PARAMS_EXIST         YNEW       N       N       N       N       Y
PARAMS_USED          YNEW       N       N       N       N       Y
REGEN_DIMS           YNEW       E       E       N       E       Y
SHEET_SIZE_INFO      YN         Y       Y       N       N       Y
STD_DTL_SETUP        YNEW       N       N       N       N       Y
SYMBOL_INFO          YN         Y       Y       N       N       Y
TABLE_CELLS          YNEW       N       N       N       N       Y
TITLE_INFO           YNEW       N       N       N       N       Y
UNUSED_MODELS        YNEW       E       E       N       E       Y
UNUSED_SHEETS        YNEW       E       E       N       N       Y
VIEW_SCALE           YNEW       N       N       N       N       Y

# ASSEMBLY REPORT CONFIGURATION
ASM_BOM              YN         Y       Y       N       N       Y
ASM_FEATURES         YN         N       N       N       N       N
BULK_ITEMS           YNEW       Y       Y       N       N       N
FRZ_COMPONENTS       YNEW       E       E       N       N       Y
GEN_COMPONENTS       YNEW       E       E       N       N       Y
GLOBAL_INTF          YNEW       N       N       N       N       N
MIS_COMPONENTS       YNEW       E       E       N       N       Y
NUM_COMPONENTS       YN         Y       Y       Y       Y       Y
SUP_COMPONENTS       YNEW       E       E       W       W       Y
PACK_COMPONENTS      YNEW       E       E       W       W       Y
UNQ_COMPONENTS       YN         Y       Y       Y       Y       Y
CIRCULAR_REFS        YNEW       W       W       N       N       N

CHILD_FAILED_FEATURES YNEW      N       N       N       N       N
CHILD_FAILED_COMPONENTS YNEW    N       N       N       N       N
FAILED_FEATURES      YNEW       N       N       N       N       N
FAILED_COMPONENTS    YNEW       N       N       N       N       N
FIXED_COMPONENTS     YNEW       N       N       N       N       N
FLEX_COMPONENTS      YNEW       N       N       N       N       N
CHILD_EXT_FAILED_FEATURES YNEW  N       N       N       N       N
CHILD_EXT_FAILED_COMPONENTS YNEW N      N       N       N       N

