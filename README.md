# mmwatch data branch

Machine-written. `.github/workflows/build.yml` pushes `data/meetings.json` here
after each build via `tools/data_branch.sh`; nothing else lives on this branch
and no human should commit to it. It exists because `main` is PR-protected and
the workflow cannot push there (issue #4). Deleting this branch resets the
meeting store to the seed committed on `main`.
