# Enterprise Offline AI RAG Platform

## ⚠️ Security Notice: Git History Warning

During a recent security audit, hardcoded secrets (such as default `SECRET_KEY` and admin passwords) were removed from the source code and moved to environment variables.

**If this repository was previously committed with those hardcoded secrets, they are still present in your git history.**

Please take the following actions immediately if this repository is public or shared:
1. **Rotate all secrets:** Treat the old `SECRET_KEY` and any previously used passwords as compromised. Generate new secure values for your production environment.
2. **Rewrite git history (Optional but recommended for public repos):** Use tools like `git filter-repo` or BFG Repo-Cleaner to completely remove the old secrets from your git history.

## Environment Variables
Before running the application, copy `backend/.env.example` to `backend/.env` and fill in the required variables (e.g., `SECRET_KEY` and `ADMIN_PASSWORD`).
