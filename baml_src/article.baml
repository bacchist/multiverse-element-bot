class Article {
  title string
  body Paragraph[] @description("The body of the article, split into paragraphs")
  url string
  publication string
  author string
  date string
  tags string[]
}

class Paper {
  title string
  body Paragraph[] @description("The text of the paper, split into paragraphs")
  figures Figure[] @description("The figures in the paper. Each figure has a caption and a url.")
  authors string[]
  date string
  tags string[]
  purpose string @description("The purpose of the paper")
}

class Paragraph {
  text string
}

class Figure {
  caption string
  url string @description("The url of the figure/image (src of the img tag). Must include the full source path.")
  height int? @description("The height of the figure/image in pixels if provided in the img tag")
  width int? @description("The width of the figure/image in pixels if provided in the img tag")
}

class ArticleSummary {
  article Article
  summary string
}

class FigureSummary {
  figure Figure
  summary string
}

class PaperSummary {
  summary Paragraph[]
}

function ParseArticle(article: string) -> Article {
  client CustomGPT41Nano
  prompt #"
    Parse the article into the following format:

    {{ ctx.output_format }}

    Article:
    {{ article }}

  "#
}

function ParsePaper(paper: string) -> Paper {
  client CustomGPT41Nano
  prompt #"
    Parse the paper into the following format:

    {{ ctx.output_format }}

    Paper:
    {{ paper }}
  "#
}

function WriteArticleSummary(article: Article) -> ArticleSummary {
  client CustomGPT41Nano
  prompt #"
    Write a summary of the article:

    {{ ctx.output_format }}

    Article:
    {{ article }}
  "#
}

function WritePaperSummary(paper: Paper) -> PaperSummary {
  client CustomGPT41Nano
  prompt #"
    Write a multi-paragraph summary of the research paper:

    {{ ctx.output_format }}

    Paper:
    {{ paper }}
  "#
}

function WriteFigureSummary(figure: image) -> FigureSummary {
  client CustomGPT41Nano
  prompt #"
    Write a summary of the figure:

    {{ ctx.output_format }}

    Figure:
    {{ figure }}
  "#
}