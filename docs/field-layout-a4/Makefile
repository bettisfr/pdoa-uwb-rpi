PDF := field-layout-a4.pdf
TEX := field-layout-a4.tex

.PHONY: all clean

all: $(PDF)

$(PDF): $(TEX)
	pdflatex -interaction=nonstopmode -halt-on-error $(TEX)

clean:
	rm -f field-layout-a4.aux field-layout-a4.log field-layout-a4.pdf
