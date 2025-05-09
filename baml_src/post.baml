class Post {
  text string @description("an insightful tweet length post about a site without the url")
  url string @description("the url of the site")
}

function WritePost(url: string, summary: string) -> Post {
  client CustomGPT41Nano
  prompt #"
    As an AI agent developer from the Multiverse School, write a tweet about this
    site that was posted to the school community chat:

    {{ ctx.output_format }}

    Site:
    {{ url }}

    Summary:
    {{ summary }}
  "#
}