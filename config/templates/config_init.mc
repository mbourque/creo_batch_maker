! INITIALIZATION file for ModelCHECK. 
!
! "I" = Interactive
! "B" = Batch
! "R" = Regeneration
! "S" = Save

! ----------------------------------------------------------
#            Options           "I"     "B"     "R"     "S"
! ----------------------------------------------------------

# Enable ModelCHECK Y=enable, N=disable, A=Ask user
MC_ENABLE        YNA            Y

# Enable/Disable ModelCHECK in specific modes
MODE_RUN         YN             Y       Y       N       N      

# Automatically update errors in models when run in BATCH
MODE_UPDATE      YN             Y       N       Y       Y      

# Enable/Disable ModelCHECK metrics in specific modes
MC_METRICS	 YN             Y       Y	Y       Y

# Directory ModelCHECK will write reports on UNIX
DIR_REPORT_U     /tmp/mc_reports

# Directory ModelCHECK will write reports
DIR_REPORT       $TEMP/mc_reports

# Directory ModelCHECK will read shape indexing files on NT
DIR_MC_DUP_READ_NT     $TEMP/mc_dup_read

# Directory ModelCHECK will read shape indexing files on UNIX
DIR_MC_DUP_READ_U    /tmp/mc_dup_read

# Directory ModelCHECK will read shape indexing files
DIR_MC_DUP_READ  $TEMP/mc_dup_read

# Directory ModelCHECK will write shape indexing files
DIR_MC_DUP_WRITE $TEMP/mc_dup_write

# Use the external  file for authorization to use Configurator Tool
MC_AUTHORIZATION_FILE	YN	N

# Asyncronous port for ModelCHECK server to use
ASYNC_PORT       3001

# Number of days to save html and xml files in DIR_REPORT
HTML_MAX_DAYS    1

# Number of items for a long list
NUM_ITEMS_LONG_LIST  100

# Auto add/upd parameter MODEL_CHECK to model with current date as it's value
ADD_DATE_PARM    YN             N       N       N       N      

# Auto add/upd parameter MC_ERRORS to model with number of errors found in model
ADD_ERR_PARM     YN             N       N       N       N      

# Auto add/upd parameter MC_CONFIG to model with current mc config used
ADD_CONFIG_PARM  YN             N       N       N       N      

# Auto add/upd parameter MC_MODE to model with current mode MC was run
ADD_MODE_PARM    YN             N       N       N       N

# Skip models in assemblies if they have not changed since being retrieved
# regardless of what MC_ERRORS is set to
SKIP_MODELS      YN             N

# Check models in assemblies regardless of whether they have changed since 
# being retrieved or not 
CHECK_ALL_MODELS YN             Y 

# Interactive SAVE MODE - pre (Y) or post (N)?
SAVE_MC_PRE      YN             N

# ASSEMBLY batch mode - run TOP only (N) or ALL LEVELS (Y)
ASM_BATCH_ALL    YN                     N

# Run MC on all drawing sheets (Y) or current only (N)
DRW_SHEET_ALL    YN	        Y	Y	Y	Y

# Config select Mode - Automatic (Y) or Load Config menu option (N)
#  or Ask User at start of Pro/E session (A)
CNFG_SELECT_AUTO YNA            Y

# Enable/Disable MC_VDA for specific mode
MC_VDA_RUN       YN             N      N       N       N

# Enable/Disable ModelUpdate 
MU_ENABLED   YN    N

# Enable/Disable ModelUpdate  for Skeleton parts
UPDATE_SKELETON  YN    N

# Enable/Disable ModelUpdate  for Sheetmetal parts
UPDATE_SHEETMETAL  YN    N

# Enable/Disable ModelUpdate  for Interchange Assembly
UPDATE_INTER_ASM  YN    N

# Enable/Disable ModelUPDATE parameter added to the model
ADD_MU_STAMP  YN    N

# Enable/Disable ModelUPDATE parameter designated
DESIGNATE_MU_STAMP  YN    N

# Enable/Disable saving of model after performing ModelUPDATE
SAVE_MU  YN    N

# Enable/Disable regenerating of model with ModelUPDATE
MU_REGENERATE  YN    N

# Highlight Color (Red,Yellow,White,Blue,Grey,Magenta,Cyan,Green,Brown)

# Duplicate models - Automatically add dup model info to text file
#   Y - always add model info 
#   N - Never add model info
#   D - add model info but Don't overwrite existing info
#   A - always Ask the user whether to add AND whether to overwrite
ADD_DUP_INFO_AUTO YNDA          D	D	N	N


# Temporary directory for preview files storage
DIR_MC_PREVIEW_U   /tmp/mc_preview

# Temporary directory for preview files storage
DIR_MC_PREVIEW   $TEMP/mc_preview

# Show Report
SHOW_REPORT       YN            Y       N       Y       Y

# PROGRAM NAMES
PROGRAM          pro

#HTML report creation
HTML_FILE_OUTPUT  YN            Y       N       Y       Y

# For Creo 12 Inseperable Assemblies
MC_RUN_ON_ASM_COMP	YN	Y	