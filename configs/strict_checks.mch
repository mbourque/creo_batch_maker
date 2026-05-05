! Configuration file for ModelCHECK. 
! Date: 04/17/2001 (2001 default)
! Date: 06/20/2001 (SS-added NOTE_CASE, LAYER_DTM_BLANK for 2002-strict)
! Date: 07/03/2001 (VA-added EXTERNAL_REFS for 2002-strict)
!                  (RJ added LAYER_EXT_ITEMS)
!                  (SS added VIEW_SCALE for 2002)
!                  (VA-added CIRCULAR_REFS for 2002-strict)
!                  (VA-added DEPENDENT FEATURE )
! Date: 06/Aug/2001 (SS Changes to FAMILY_VERIFY for 2002)
! Date: 03/Aug/2001 (AMN added YNEW for IMPORT_FEAT)
! Date: 03/Aug/2001 (AMN added DESIGNATED_ATTR)
! Date: 25/Sep/2001 (VA Remove EXT_REF_INFO)
! Date: 19/Feb/2002 (VA refs to EXTERNAL_DEPS)
! Date: 02/May/2002 (SS defaults for Pro/E 2002 alpha release)
! Date: 30/July/2002 (RJ: Corrected spell for SMALL_CYLSRF)
! Date: 13/Mar/2003 (RJ: Added CHILDREN_EXIST)
! 06-Feb-07 L-01-26 $$1 vmishra removed DRAWING_GTOLS.
! 25-Apr-22 Q-10-16 $$2 ksingh  Marked Matrics colum as Y by default.
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
ADD_CHK_PARAM        YN         Y       Y       N       N       Y
BURIED_FEAT          YNEW       E       E       E       E       Y
CHAMFER_CHILD        YNEW       E       E       E       E       Y
CHILDREN_EXIST       YNEW       E       E       E       E       Y
COSMETIC_FEAT        YNEW       Y       Y       N       N       Y
CYL_CUT_SLOTS        YNEW       E       W       N       W       Y
CYL_DIAMS            YNEW       Y       Y       N       N       Y
DATUM_RENAME         YNEW       W       Y       N       N       Y
DEF_DENSITY          YNEW       E       Y       E       E       Y
DEFAULT_CHILD        YN         Y       Y       N       N       Y
DRAFT_ANGLES         YNEW       Y       Y       N       N       Y
DRAFT_CHILD          YNEW       W       W       W       W       Y
DTM_AXES_INFO        YN         Y       Y       N       N       Y
DTM_CSYS_INFO        YN         Y       Y       N       N       Y
DTM_CURVE_INFO       YN         Y       Y       N       N       Y
DTM_PLANE_INFO       YN         Y       Y       N       N       Y
DTM_POINT_INFO       YN         Y       Y       N       N       Y
DUPLICATE_MODELS     YNEW       E       E       W       W       Y
EARLY_CHAMFER        YNEW       E       W       N       N       Y
EARLY_COSMETIC       YNEW       W       W       N       N       Y
EARLY_DRAFT          YNEW       E       E       N       N       Y
EARLY_ROUND          EENN       E       E       N       N       Y
EDGE_REFERENCES      YNEW       E       E       E       E       Y
EXTRA_LAYERS         YNEW       W       W       N       N       Y
EXTRA_PARAMS         YNEW       W       W       N       N       Y
FAMILY_INFO          YNEW       E       E       E       E       Y
FEATURE_INFO         YN         Y       Y       N       N       Y
FILE_SIZE            YN         Y       Y       N       N       Y
FREEFORM             YN         Y       Y       N       N       Y
FT_DEF_VALS          YNEW       E       Y       W       N       Y
FT_STD_PARMS         YNEW       E       Y       W       N       Y
GEOM_CHECKS          YNEW       E       E       N       E       Y
GEOMETRIC_TOL        YN         Y       Y       N       N       Y
HOLE_DIAMS           YNEW       Y       Y       N       N       Y
IGNORE_FEAT          YN         Y       Y       N       Y       Y
IMPORT_FEAT          YNEW       Y       Y       N       N       Y
INCOMPLETE_FEAT      YNEW       E       W       N       N       Y
INSERT_MODE          YNEW       E       W       N       N       Y
INSTANCE_NAME        YNEW       W       Y       N       N       Y
LAYER_DISPSTAT       YNEW       W       W       W       W       Y
LAYER_DTM_BLANK      YNEW       E       E       E       E       Y
LAYER_EXT_ITEMS      YNEW       E       E       E       E       Y
LAYER_INFO           YN         Y       Y       N       N       Y 
LAYER_MOVE           YNEW       W       Y       N       N       Y
LAYER_PLACE          YNEW       W       W       W       W       Y
LAYER_STATUS         YNEW       W       W       W       W       Y
LAYOUT_INFO          YN         Y       Y       N       N       Y
LOW_TOLERANCE        YNEW       Y       Y       N       N       Y
MATERIAL_INFO        YNEW       Y       Y       W       N       Y
MEMORY_SPACE         YN         Y       Y       N       N       Y
MERGE_FEAT           YNEW       Y       Y       N       E       Y
MINMAXTOL_INFO       YN         Y       Y       N       N       Y
MODEL_NAME           YNEW       E       E       N       W       Y
MODEL_NAME_STR       YN         Y       Y       N       N       Y
NAMED_FEAT           YN         Y       Y       N       N       Y
OVERALL_SIZE         YN         Y       Y       N       N       Y
PARAM_INFO           YN         Y       Y       N       N       Y
PARAM_NOTE_REQ       YNEW       E       W       N       N       Y
PARAM_NOTE_UNACC     YNEW       E       W       N       N       Y
PARAM_RENAME         YNEW       W       W       N       Y       Y
PARAM_SPELL          YNEW       E       E       N       W       Y
PARAM_UNUSED         YNEW       N       N       N       N       Y
PARAMCHECK           YNEW       E       E       N       W       Y
PLANE_CHILD          YNEW       E       E       N       N       Y
PLANE_PARENT         YNEW       E       E       N       N       Y
PRO_VERSION          YNEW       E       E       W       W       Y
RC_INCOMPLETED       YNEW       E       W       N       N       Y
REG_FEATURES         YN         Y       Y       N       N       Y
REGEN_ERRS           YNEW       E       E       N       N       Y
REGEN_WARN           YNEW       W       W       N       N       Y
REGEN_WRNS           YNEW       W       N       N       N       Y
RELATION_COMM        YNEW       W       W       W       W       Y
RELATION_ERRS        YNEW       W       E       N       N       Y
RELATION_INFO        YN         Y       Y       N       N       Y
RELATION_MISS        YNEW       W       W       W       W       Y
RELATION_MULT        YNEW       W       W       W       W       Y
RENAMED_SYMBOLS      YN         Y       N       Y       N       Y
REPT_LAYR_ALWAYS	 YN		    Y	    Y	    Y	    Y       Y
ROUND_CHILD          YNEW       E       E       E       E       Y
RULECHECK_INFO       YN         Y       Y       N       N       Y
SHARP_EDGES          YNEW       E       E       N       N       Y
SHORT_EDGES          YNEW       E       E       N       E       Y
SHTMTL_BENDTAB       YNEW       E       E       N       E       Y
SHTMTL_FLAT          YNEW       E       E       N       E       Y
SHTMTL_THICK         YNEW       E       E       N       E       Y
SHTMTL_UNBENDS       YNEW       E       E       N       E       Y
SHTMTL_YFACTOR       YN         Y       Y       N       N       Y
SIMPREP_INFO         YN         Y       Y       N       N       Y
SIMPREP_NAME         YNEW       E       E       N       N       Y
SKETCH_ITEMS         YNEW       E       E       E       E       Y
SLA_INFO             YNEW       E       E       N       N       Y
SMALL_CYLSRF         YNEW       E       E       N       W       Y
SRF_EDGES            YNEW       E       E       N       N       Y
STARTCHECK           YNEW       E       E       N       W       Y 
SUP_FEATURES         YNEW       W       W       N       W       Y
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
DIM_MODEL_SHOWN      YNEW       E       Y       N       N       Y
DIM_OVERWRITE        YNEW       E       E       N       E       Y
DIM_SHOWN_CREAT      YNEW       E       Y       N       N       Y
DRAFT_GEOM           YNEW       E       E       N       E       Y
DRAWING_LAYERS       YNEW       E       E       N       E       Y
DRAWING_PARAMS       YNEW       E       E       N       E       Y
DRAWING_NAME         YNEW       W       W       N       W       Y
DEFAULT_VIEWS        YNEW       E       E       N       E       Y
ERASED_VIEWS         YNEW       W       W       N       W       Y
FORMAT_NAME          YNEW       E       E       N       E       Y
IGNORE_SHEETS        YN         Y       Y       Y       Y       Y
MODELS_USED          YN         Y       Y       Y       N       Y
NOTE_CASE            YNEW       E       E       N       E       Y
NOTE_FONT            YNEW       E       E       N       E       Y
NOTE_HEIGHT          YNEW       E       E       N       E       Y
NOTE_INFO            YN         Y       Y       N       N       Y
NOTE_SPELL           YNEW       E       E       N       E       Y
TITLE_SPELL          YNEW       E       E       N       E       Y
SYMBOL_SPELL         YNEW       N       N       N       N       Y
NOTE_UNACCEPT        YNEW       E       E       Y       N       Y
NUM_DRAW_SHEETS      YNEW       E       E       W       W       Y
OVERLAP_INFO         YNEW       E       E       N       E       Y
PARAMS_EXIST         YNEW       N       N       N       N       Y
PARAMS_USED          YNEW       E       E       N       E       Y
REGEN_DIMS           YNEW       E       E       N       E       Y
SHEET_SIZE_INFO      YN         Y       Y       N       N       Y
STD_DTL_SETUP        YNEW       E       E       N       E       Y
SYMBOL_INFO          YN         Y       Y       N       N       Y
TABLE_CELLS          YNEW       E       E       Y       N       Y
TITLE_INFO           YNEW       W       W       N       W       Y
UNUSED_MODELS        YNEW       E       E       N       E       Y
UNUSED_SHEETS        YNEW       E       E       N       N       Y
VIEW_SCALE           YNEW       E       E       N       E       Y


# ASSEMBLY REPORT CONFIGURATION
ASM_BOM              YN         Y       Y       N       N       Y
ASM_FEATURES         YN         Y       Y       N       N       Y
BULK_ITEMS           YNEW       Y       Y       N       N       Y
FRZ_COMPONENTS       YNEW       E       E       N       N       Y
GEN_COMPONENTS       YNEW       E       E       N       N       Y
GLOBAL_INTF          YNEW       E       E       N       N       Y
MIS_COMPONENTS       YNEW       E       E       N       N       Y
NUM_COMPONENTS       YN         Y       Y       Y       Y       Y
SUP_COMPONENTS       YNEW       E       E       W       W       Y
PACK_COMPONENTS      YNEW       E       E       W       W       Y
UNQ_COMPONENTS       YN         Y       Y       Y       Y       Y
CIRCULAR_REFS        YNEW       W       W       N       N       Y
