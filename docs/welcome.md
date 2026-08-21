# ParqDB Knowledgebase

ParqDB Knowledgebase turns Markdown documentation into a static vector-search
site. The source table and IVF-LVQ8 index are stored as Parquet, while the
browser embeds questions and reads only the required HTTP byte ranges.

## Why serverless search?

Static publication removes the query server from the request path. A knowledge
base can live on GitHub Pages or object storage, and a question never needs to
leave the browser. Search results link directly to the original documentation.
