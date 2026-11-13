You are publishing one new Block Talks video as a podcast episode on theblockopedia.com.
Work only inside this folder. Video ID: {{VIDEO_ID}}. Mode: {{MODE}}.

## Steps

1. Run `python3 publish.py fetch {{VIDEO_ID}}`. It prints the video's title, description,
   chapters and upload date, and downloads the audio. If it prints `"ok": false`, stop and
   reply with that error in one line.
2. Write the SEO copy to `work/{{VIDEO_ID}}/spec.json` (format below), using only facts from
   the title and description. Never invent numbers, roles, companies or links.
3. Run `python3 publish.py publish {{VIDEO_ID}} work/{{VIDEO_ID}}/spec.json --status {{MODE}}`.
4. Reply with one line: the episode number, status, title and URL from the result, or the error.

## spec.json format

```json
{
  "title": "How Sweatcoin Lets You Earn Crypto by Walking | Oleg Fomenko, Founder",
  "hook": "How did a move-to-earn idea grow to over 120 million registered users? Oleg Fomenko, founder of Sweatcoin, explains the business model, retention and the road to profitability.",
  "learn": ["How Sweatcoin was born and grew so fast", "Sweatcoin's plan to reach profitability", "How Sweatcoin keeps 120 million users engaged"],
  "links": [["Oleg Fomenko on LinkedIn", "https://www.linkedin.com/in/ofomenko/"], ["Sweatcoin", "https://www.sweatcoin.com"]],
  "seo": "Sweatcoin: Earn Crypto by Walking | Block Talks",
  "meta": "Sweatcoin founder Oleg Fomenko on move-to-earn, growing to 120M+ users, retention, profitability and bringing Web3 to the mass market.",
  "kw": "sweatcoin",
  "chapters": [[0, "Introduction"], [95, "How Sweatcoin started"]]
}
```

Rules:

- `title`: a clear, searchable topic first, then ` | ` and the guest's name (and company or role
  if the description gives it). At most 90 characters. No clickbait, no emojis, no "Ft.".
- `hook`: 2 sentences, about 30–45 words. Open with the question the episode answers, then
  who the guest is and what they cover.
- `learn`: 4–6 short bullets, each a concrete takeaway from the description or chapters.
- `links`: only links that appear in the YouTube description and belong to the guest or their
  company (LinkedIn, X, website). Leave out Blockopedia's own links, sponsors and hashtags.
  Use `[]` when there are none. The YouTube link and the Block Talks page are added for you.
- `seo`: at most 60 characters, ending with ` | Block Talks`.
- `meta`: 140–160 characters, one sentence, names the guest and the main topics.
- `kw`: the 1–3 word phrase people would search for this episode.
- `chapters`: the video's chapters with clean, sentence-case titles (fix typos, keep the start
  seconds from fetch). Leave the key out if the video has no chapters.
- Write in plain English. Use straight quotes in JSON.
