class Post {
  text string @description("an insightful tweet length post about a site without the url. 280 characters max")
  url string? @description("url of the article or paper. If this post is from a thread, only include this in the first post")
  image_url string? @description("url of a figure from the article or paper. Include the full source path.")
}

class Thread {
  url string
  posts Post[]
}

function WritePost(url: string, summary: string) -> Post {
  client CustomGPT41Mini
  prompt #"
    As an AI agent developer from the Multiverse School, write a casual tweet about this site that was posted to the school community chat.

    Site:
    {{ url }}

    Summary:
    {{ summary }}

    Strip filler. Sharpen verbs. Ground each tweet in utility, specificity, and human cadence. Avoid redundant enthusiasm, vague claims, and multi-topic sprawl.

    Keep each post focused on one benefit. Remove all exclamation marks. Cut all abstract modifiers unless quantifiable. Never lead with 'exciting,' 'perfect,' or 'amazing'.

    {{ ctx.output_format }}
  "#
}

function WriteThread(url: string, summary: string, figures: FigureSummary[]) -> Thread {
  client CustomGPT41Mini
  prompt #"
    Using the provided summary, create an engaging and insightful multi-post
    thread about the research paper. Start with an introductory post, and finish
    with a conclusion. Include a figure from the paper in each post after the first post.

    Paper URL:
    {{ url }}

    Summary:
    {{ summary }}

    Figures:
    {% for figure in figures %}
      {{ figure.summary }}
      {{ figure.figure.url }}
    {% endfor %}

    Strip filler. Sharpen verbs. Ground each tweet in utility, specificity, and human cadence. Avoid redundant enthusiasm, vague claims, and multi-topic sprawl. Remove all exclamation marks. Cut all abstract modifiers unless quantifiable. Never lead with 'exciting,' 'perfect,' or 'amazing'.

    {{ ctx.output_format }}
  "#
}