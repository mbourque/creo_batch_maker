! INITIALIZATION file for ModelCHECK. 
! This file is to initialize MC. It is read only once.
! Demonstration Configuration file for ModelCHECK version 2002
! This file is to be used with the ModelCHECK wheel Pro/ENGINEER demo parts.
! Updated 07-05-2004.
!
!  7-Feb-00 AZh Removed LF.
!  8-Jun-00 $$1 AMN Make comments more understandable. Get rid of EWNY detail.
!               Add APPLET_WIDTH option
! 10-Oct-00 $$2 AMN Choice added to ADD_DUP_INFO_AUTO
! 11-Nov-00 $$3 AMN Choice added TEXT_FILE_OUTPUT   O
! 11-Dec-00 $$4 AMN Increase default APPLET_WIDTH 
! 13-Feb-01 $$5 SS  Removed APPLET_WIDTH and introduced WINDOW_WIDTH and 
!                   WINDOW_HEIGHT - WINDOW_WIDTH now will control the width
!                   of the applet
! 13-Jul-01 $$6 AMN Added VDA_GUI
! 11-Dec-01 $$7 VA/SS Pro/Intralink search/preview
! 27-Dec-01 $$8 RJ  Changed NETSCAPE to BROWSER
! 05-Jan-02 $$9 SS  Changed definition for MODE_VIEW..default to be changed later
! 18-Feb-02 $$10 RJ  Fixed changed for SPR901977
! 16-Apr-02 $$11 RJ  Added SHOW_REPORT SPR933571
! 02-May-02 $$12 SS  Config changes for Pro/E-2002 alpha release
! 28-May-02 $$13 SS  DIR_TRAIL option removed to use config.pro
!                    option trail_dir instead
! 11-Jun-02 $$14 RJ  Replaced BROWSER option with USE_EMBEDDED_BROWSER
! 11-Jun-02      VA  hashed out few options  SPR936957
! 05-Aug-02 $$15 SS  SKIP_MODELS option
! 13-Aug-02      RJ  SHOW_REPORT individual setting for all four modes
! 27-Aug-02 $$16 SS  CHECK_ALL_MODELS option
! 08-Oct-02 $$17 RJ  Changes for no support to standalone browser
! 04-Feb-03 $$18 VA  optional advanced checking buried feats BURIED_ADVANCED
! 23-Mar-03 $$19 RJ  removed TEXT_FILE_OUTPUT
! 07-Apr-03 $$20 RJ  Added ENABLE_CNFG_EDIT,ALLOW_CNFG_SELECT,ALLOW_CONDITION_EDIT
!                    and removed CNFG_SELECT_AUTO
! 16-Sep-03 $$21 RJ  Obsoleted ENABLE_CNFG_EDIT,ALLOW_CNFG_SELECT,ALLOW_CONDITION_EDIT
!                    and VDA_GUI
! 15-Jan-04 K-01-22 $$22 VA  added html option
! 23-May-04 K-03-02 $$23 rjain  added config backup option
! 05-Jul-04 K-03-05 $$24 rjain  added mc_authorization_file
! 21-Apr-05 K-03-23 $$25 rjain  reinstated CNFG_SELECT_AUTO
! 12-Sep-05 K-03-31 $$26 rjain  added NUM_ITEMS_LONG_LIST
! 11-Jun-06 L-01-10 $$27 rjain  added few more for MU project
! 25-Jun-14 P-20-55 $$28 anath  SPR 1101609 - Remove HIGHLIGHT_COLOR & PARENT_HI_COLOR.
! 10-Sep-19 P-20-27 $$29 prmore  SPR 6081250: Removed obslete option INTRALINK_DUPINFO.
!
! "I" = Interactive
! "B" = Batch
! "R" = Regeneration
! "S" = Save

! ----------------------------------------------------------
#            Options           "I"     "B"     "R"     "S"
! ----------------------------------------------------------

# Enable ModelCHECK Y=enable, N=disable, A=Ask user
MC_ENABLE	YNA	Y	Y	Y	N

# Enable/Disable ModelCHECK in specific modes
MODE_RUN	YN	Y	Y	N	N      

# Automatically update errors in models when run in BATCH
MODE_UPDATE	YN	N	N	N	N      

# Enable/Disable ModelCHECK metrics in specific modes
MC_METRICS	YN	N	N	Y	Y

# Directory ModelCHECK will write reports on NT
#DIR_REPORT_NT	$TEMP/mc_reports

# Directory ModelCHECK will write reports on UNIX
DIR_REPORT_U	/tmp/mc_reports

# Directory ModelCHECK will write reports
DIR_REPORT	$TEMP/mc_reports

# Directory ModelCHECK will write metrics flat file on NT
#DIR_METRICS_NT	$TEMP/mc_metrics

# Directory ModelCHECK will write metrics flat file on UNIX
#DIR_METRICS_U	/tmp/mc_metrics

# Directory ModelCHECK will write metrics flat file
# DIR_METRICS	$TEMP/mc_metrics

# Directory ModelCHECK will read shape indexing files on NT
DIR_MC_DUP_READ_NT	$TEMP/mc_dup_read

# Directory ModelCHECK will read shape indexing files on UNIX
DIR_MC_DUP_READ_U	/tmp/mc_dup_read

# Directory ModelCHECK will read shape indexing files
DIR_MC_DUP_READ	$TEMP/mc_dup_read

# Directory ModelCHECK will write shape indexing files on NT
#DIR_MC_DUP_WRITE_NT	$TEMP/mc_dup_write

# Directory ModelCHECK will write shape indexing files on UNIX
# DIR_MC_DUP_WRITE_U	/tmp/mc_dup_write

# Directory ModelCHECK will write shape indexing files
DIR_MC_DUP_WRITE	$TEMP/mc_dup_write

# Directory ModelCHECK will keep the backup of config files on NT
#DIR_MC_BACKUP_CONFIG_NT	$TEMP/mc_backup_config

# Directory ModelCHECK will keep the backup of config files on UNIX
#DIR_MC_BACKUP_CONFIG_U	/tmp/mc_backup_config

# Directory ModelCHECK will keep the backup of config files
#DIR_MC_BACKUP_CONFIG	$TEMP/mc_backup_config

# Use the external  file for authorization to use Configurator Tool
MC_AUTHORIZATION_FILE	YN	N

# Asyncronous port for ModelCHECK server to use
ASYNC_PORT	3001

# Number of days to save html and xml files in DIR_REPORT
HTML_MAX_DAYS	1

# Number of items for a long list
NUM_ITEMS_LONG_LIST	100

# Auto add/upd parameter MODEL_CHECK to model with current date as it's value
ADD_DATE_PARM	YN	N	N	N	N      

# Auto add/upd parameter MC_ERRORS to model with number of errors found in model
ADD_ERR_PARM	YN	N	N	N	N      

# Auto add/upd parameter MC_CONFIG to model with current mc config used
ADD_CONFIG_PARM	YN	N	N	N	N      

# Auto add/upd parameter MC_MODE to model with current mode MC was run
ADD_MODE_PARM	YN	N	N	N	N

# Skip models in assemblies if they have not changed since being retrieved
# regardless of what MC_ERRORS is set to
SKIP_MODELS	YN	N

# Check models in assemblies regardless of whether they have changed since 
# being retrieved or not 
CHECK_ALL_MODELS	YN	Y 

# Interactive SAVE MODE - pre (Y) or post (N)?
SAVE_MC_PRE	YN	N

# ASSEMBLY batch mode - run TOP only (N) or ALL LEVELS (Y)
ASM_BATCH_ALL	YN	Y

# Run MC on all drawing sheets (Y) or current only (N)
DRW_SHEET_ALL	YN	Y	Y	Y	Y

# Config select Mode - Automatic (Y) or Load Config menu option (N)
#  or Ask User at start of Pro/E session (A)
CNFG_SELECT_AUTO	YNA	Y

# Enable/Disable MC_VDA for specific mode
MC_VDA_RUN	YN	N	N	N	N

# Enable/Disable ModelUpdate 
MU_ENABLED	YN	N

# Enable/Disable ModelUpdate  for Skeleton parts
UPDATE_SKELETON	YN	N

# Enable/Disable ModelUpdate  for Sheetmetal parts
UPDATE_SHEETMETAL	YN	N

# Enable/Disable ModelUpdate  for Interchange Assembly
UPDATE_INTER_ASM	YN	N

# Enable/Disable ModelUPDATE parameter added to the model
ADD_MU_STAMP	YN	N

# Enable/Disable ModelUPDATE parameter designated
DESIGNATE_MU_STAMP	YN	N

# Enable/Disable saving of model after performing ModelUPDATE
SAVE_MU	YN	N

# Enable/Disable regenerating of model with ModelUPDATE
MU_REGENERATE	YN	N

# Highlight Color (Red,Yellow,White,Blue,Grey,Magenta,Cyan,Green,Brown)

# Duplicate models - Automatically add dup model info to text file
#   Y - always add model info 
#   N - Never add model info
#   D - add model info but Don't overwrite existing info
#   A - always Ask the user whether to add AND whether to overwrite
ADD_DUP_INFO_AUTO	YNDA	N	N	N	N

# Temporary directory for preview files storage
#DIR_MC_PREVIEW_NT	$TEMP/mc_preview

# Temporary directory for preview files storage
DIR_MC_PREVIEW_U	/tmp/mc_preview

# Temporary directory for preview files storage
DIR_MC_PREVIEW	$TEMP/mc_preview

# Advance buried feature analysis 
BURIED_ADVANCED	YN	Y

# Show Report
SHOW_REPORT	YN	Y	N	Y	Y

# PROGRAM NAMES
PROGRAM	pro

#HTML report creation
HTML_FILE_OUTPUT	YN	Y	Y	Y	Y

# For Creo 12 Inseperable Assemblies
MC_RUN_ON_ASM_COMP	YN	Y	

# Check all MBD annotations throughout the model hierarchy.
MC_CHECK_ALL_LEVEL_MBD_ANNTNS	YN	Y

# Verify family table instances regenerate correctly.
MCREGEN_VERIFY_FT_INSTS	YN	Y

# Ignore driving dimensions when evaluating MBD dimensions.
MC_MBD_IGNORE_DRIVING_DIMS	YN	N

# Get version information from model metadata.
MC_GET_VERSION_FROM_META_DATA	YN	Y

# Report errors in merged components found in top-level assemblies.
MC_MRG_COMP_ERR_IN_TOP_ASM	YN	Y

# Report errors in embedded merged components.
MC_MRG_EMBED_COMP_ERR	YN	Y

# Report the master material assigned to the model.
MC_REPORT_MASTER_MATERIAL	YN	Y

# Recompute mass properties before performing mass-related checks.
MU_MASS_RECOMPUTE	YN	N