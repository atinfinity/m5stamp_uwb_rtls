OPENSCAD ?= /Applications/OpenSCAD-2021.01.app/Contents/MacOS/OpenSCAD
ASSETS   := ../../docs/assets
PNGOPTS  := --imgsize=1600,1200 --viewall --autocenter --colorscheme Tomorrow --render

STL := stl/anchor_mount.stl stl/tag_case_body.stl stl/tag_case_lid.stl
PNG := $(ASSETS)/cad-anchor-mount.png $(ASSETS)/cad-tag-case.png

all: $(STL) $(PNG)

stl/anchor_mount.stl: anchor_mount.scad common.scad
	$(OPENSCAD) --export-format binstl -o $@ $<

stl/tag_case_body.stl: tag_case.scad common.scad
	$(OPENSCAD) --export-format binstl -o $@ -D 'part="body"' $<

stl/tag_case_lid.stl: tag_case.scad common.scad
	$(OPENSCAD) --export-format binstl -o $@ -D 'part="lid"' $<

$(ASSETS)/cad-anchor-mount.png: anchor_mount.scad common.scad
	$(OPENSCAD) $(PNGOPTS) -D 'preview=true' -o $@ $<

$(ASSETS)/cad-tag-case.png: tag_case.scad common.scad
	$(OPENSCAD) $(PNGOPTS) -o $@ -D 'part="preview"' $<

clean:
	rm -f $(STL) $(PNG)

.PHONY: all clean
