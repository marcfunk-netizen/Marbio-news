name: Marbio News Daily Update
on:
  schedule:
    - cron: '0 5 * * *'
  workflow_dispatch:
jobs:
  update-marbio:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install requests anthropic
      - name: Run Marbio updater
        env:
          TAVILY_API_KEY: ${{ secrets.TAVILY_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python update_marbio.py
      - name: Commit and push
        run: |
          git config user.name "Marbio Bot"
          git config user.email "marbio-bot@users.noreply.github.com"
          git add index.html
          git diff --cached --quiet || git commit -m "📰 Marbio News — $(date +'%d %B %Y')"
          git push --force origin main
