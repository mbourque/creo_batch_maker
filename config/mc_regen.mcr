# ModelCHECK Regen Config file (amn) 9-27-99
# 17-Oct-01 J-03-10   VA  $$1   modify error string center->origin
# 11-Aug-15 P-30-13 ngarad $$2 Added new message
# 01-Oct-19 P-70-29 ksingh $$3 Added new generic message for multibody
# This file contains a list of strings to search for among the lines that
# are output when MC Regen is run. The format is either 
# E:strings or W:strings   
# E means to consider all matching lines to be errors
# W means to consider all matching lines to be warnings

E:ERROR
E:Error
E:error

E:Reference for the section entity no longer exists
E:Regeneration failed
E:Reference and its parent feature for the section entity no longer exist
E:Reference and its parent feature no longer exist
E:currently frozen
E:The geometry which serves as the origin
E:Feature references are missing
E:Cannot intersect part
E:ASSEMBLY CUT is entirely outside the model
E:has reference to generic assembly
E:circular references found
E:unattached feature(s)
E:Invalid external reference for the section entity is encountered
E:Some relations are no longer satisfied
E:Invalid left side of assignment
E:entirely outside the model.

W:WARNING
W:Warning
W:warning

W:External reference not present
W:CUT is entirely outside
W:Design intent is unclear
W:Model changed since mass props calculated
W:One sided edge found
W:has been frozen.
W:Relations have errors/warnings
W:Cannot update placement of component
W:Model geometry for drawing is missing
W:CUT is entirely outside the model
W:PROTRUSION is entirely inside the model
W:suppressed feature(s) or component(s)
W:family table driven and will use pre-Wildfire3 replace functionality
W:Invalid symbol
W:Some constraint relations are no longer satisfied
W:Invalid data type combination at left side of expression
W:contains obsolete dimension
W:External ref. for feature/component not found
W:Cannot update placement of component