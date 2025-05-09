class Post {
  text string @description("an insightful tweet length post about a site without the url")
  url string @description("the url of the site")
}

function WritePost(url: string, summary: string) -> Post {
  client CustomGPT4oMini
  prompt #"
    Write a tweet length post about the following site:

    {{ ctx.output_format }}

    Site:
    {{ url }}

    Summary:
    {{ summary }}
  "#
}