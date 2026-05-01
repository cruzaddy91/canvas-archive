output "archive_repos" {
  description = "Provisioned archive repos with their clone URLs and metadata."
  value = {
    for slug, repo in github_repository.archive : slug => {
      name      = repo.name
      ssh_url   = repo.ssh_clone_url
      https_url = repo.http_clone_url
      html_url  = repo.html_url
    }
  }
}
