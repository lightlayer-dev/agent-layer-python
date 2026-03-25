# Publishing to PyPI

This package uses **Trusted Publishing** (OIDC) via GitHub Actions — no API tokens needed once configured.

## First-Time Setup

### 1. Create a PyPI Account

1. Go to [pypi.org](https://pypi.org) and create an account (or sign in)
2. Enable 2FA (required for publishing)

### 2. Configure Trusted Publishing on PyPI

Since the package hasn't been published yet, use PyPI's "pending publisher" flow:

1. Go to [pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
2. Under **"Add a new pending publisher"**, fill in:
   - **PyPI project name:** `agent-layer`
   - **Owner:** `lightlayer-dev`
   - **Repository:** `agent-layer-python`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. Click **"Add"**

### 3. Create the GitHub Environment

1. Go to the repo **Settings → Environments**
2. Create an environment called `pypi`
3. Optionally add protection rules (e.g., require approval before publishing)

### 4. Publish!

**Option A: Tag-based publish (recommended)**

```bash
# Make sure version in pyproject.toml matches the tag
git tag v0.1.0
git push origin v0.1.0
```

The workflow triggers automatically on `v*` tags.

**Option B: Manual publish**

1. Go to **Actions → Publish to PyPI**
2. Click **"Run workflow"**
3. Select the branch and click **"Run workflow"**

## Versioning

- Version lives in `pyproject.toml` under `[project] version`
- Follow [semver](https://semver.org/): `MAJOR.MINOR.PATCH`
- Tag format: `v0.1.0`, `v0.2.0`, `v1.0.0`, etc.
- Always update the version in `pyproject.toml` **before** tagging

### Version Bump Workflow

```bash
# 1. Update version in pyproject.toml
# 2. Commit the change
git add pyproject.toml
git commit -m "chore: bump version to 0.2.0"

# 3. Tag and push
git tag v0.2.0
git push origin main --tags
```

## Alternative: API Token Publishing

If trusted publishing doesn't work for some reason, you can fall back to API tokens:

1. On PyPI, go to **Account Settings → API tokens**
2. Create a token scoped to the `agent-layer` project
3. In the GitHub repo, go to **Settings → Secrets → Actions**
4. Add a secret named `PYPI_API_TOKEN` with the token value
5. Update `.github/workflows/publish.yml` to replace the trusted publishing step:

```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

## Verifying the Publish

After publishing, check:
- [pypi.org/project/agent-layer/](https://pypi.org/project/agent-layer/)
- `pip install agent-layer` should work
- `pip install agent-layer[fastapi]` for framework extras
