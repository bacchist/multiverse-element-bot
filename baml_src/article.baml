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

function ParseArticle(article: string) -> Article {
  client CustomGPT4oMini
  prompt #"
    Parse the article into the following format:

    {{ ctx.output_format }}

    Article:
    {{ article }}

  "#
}