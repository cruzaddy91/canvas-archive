resource "github_repository" "archive" {
  for_each = var.courses

  name        = "${var.repo_prefix}-${each.key}"
  description = "Archive of ${each.value.code} (${each.value.term}): ${each.value.name}"
  visibility  = "private"

  has_issues      = false
  has_projects    = false
  has_wiki        = false
  has_discussions = false

  auto_init = true

  delete_branch_on_merge = true
  archive_on_destroy     = true

  topics = [
    "canvas-archive",
    lower(replace(each.value.code, "-", "")),
    lower(each.value.term),
  ]
}

resource "github_branch_default" "main" {
  for_each = var.courses

  repository = github_repository.archive[each.key].name
  branch     = "main"
}

resource "github_repository_file" "readme" {
  for_each = var.courses

  repository = github_repository.archive[each.key].name
  branch     = "main"
  file       = "README.md"
  content = templatefile("${path.module}/templates/README.md.tftpl", {
    code        = each.value.code
    name        = each.value.name
    term        = each.value.term
    canvas_id   = each.value.canvas_id
    archived_at = formatdate("YYYY-MM-DD", timestamp())
  })
  commit_message      = "Initial README"
  overwrite_on_create = true

  lifecycle {
    ignore_changes = [content, commit_message]
  }
}

resource "github_repository_file" "gitignore" {
  for_each = var.courses

  repository          = github_repository.archive[each.key].name
  branch              = "main"
  file                = ".gitignore"
  content             = file("${path.module}/templates/gitignore.tftpl")
  commit_message      = "Initial .gitignore"
  overwrite_on_create = true

  lifecycle {
    ignore_changes = [content, commit_message]
  }
}

resource "github_repository_file" "gitattributes" {
  for_each = var.courses

  repository          = github_repository.archive[each.key].name
  branch              = "main"
  file                = ".gitattributes"
  content             = file("${path.module}/templates/gitattributes.tftpl")
  commit_message      = "Initial .gitattributes (Git LFS rules)"
  overwrite_on_create = true

  lifecycle {
    ignore_changes = [content, commit_message]
  }
}

# TODO: Branch protection on private repos requires GitHub Pro on free accounts.
# Switch to github_repository_ruleset (works on free private repos) when we revisit
# protection. For now, force-pushes and deletions are guarded only by the
# warn-before-destructive-ops rule on the operator side.
