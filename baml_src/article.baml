class Article {
  title string
  body Paragraph[] @description("The body of the article, split into paragraphs")
  url string
  publication string
  author string
  date string
  tags string[]
}

class Paragraph {
  text string
}

class ArticleSummary {
  article Article
  summary string
}

function ParseArticle(article: string) -> Article {
  client CustomGPT4oMini
  prompt #"
    Parse the article into the following format:

    {{ ctx.output_format }}

    Article:
    {{ article }}

  "#
}

function WriteArticleSummary(article: Article) -> ArticleSummary {
  client CustomGPT4oMini
  prompt #"
    Write a summary of the article:

    {{ ctx.output_format }}

    Article:
    {{ article }}
  "#
}
