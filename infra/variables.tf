variable "github_owner" {
  type        = string
  description = "GitHub user or org that owns the archive repos."
  default     = "cruzaddy91"
}

variable "repo_prefix" {
  type        = string
  description = "Prefix prepended to every archive repo name (keeps them clustered alphabetically)."
  default     = "canvas-archive"
}

variable "courses" {
  type = map(object({
    canvas_id = number
    code      = string
    name      = string
    term      = string
  }))
  description = <<-EOT
    Courses to provision archive repos for.
    Map key is the repo slug (e.g. "cmpt-355-compilers"); full repo name = "$${var.repo_prefix}-$${key}".
  EOT
  default     = {}
}
