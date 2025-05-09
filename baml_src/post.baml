class Post {
  text string @description("an insightful tweet length post about a site without the url")
  url string @description("the url of the site")
}

function WritePost(url: string, summary: string) -> Post {
  client CustomGPT41Nano
  prompt #"
    As an AI agent developer from the Multiverse School, write a casual tweet about this site that was posted to the school community chat.

    Site:
    {{ url }}

    Summary:
    {{ summary }}

    Strip filler. Sharpen verbs. Ground each tweet in utility, specificity, and human cadence. Avoid redundant enthusiasm, vague claims, and multi-topic sprawl.

    Keep each post focused on one benefit. Remove all exclamation marks. Cut all abstract modifiers unless quantifiable. Never lead with 'exciting,' 'perfect,'
    or 'amazing'.

    {{ ctx.output_format }}
  "#
}