# Immutable-tag ECR repositories for Phase 9 freeze images. Frontend ships on
# Vercel; API/worker/crawl-proxy/parser-sandbox pull from ECR on the instance.

locals {
  ecr_repos = toset([
    "smart-rag-api",
    "smart-rag-worker",
    "smart-rag-crawl-proxy",
    "smart-rag-parser-sandbox",
  ])
}

resource "aws_ecr_repository" "app" {
  for_each             = local.ecr_repos
  name                 = each.value
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}
