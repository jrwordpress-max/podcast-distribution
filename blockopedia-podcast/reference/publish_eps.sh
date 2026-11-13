#!/bin/zsh
# Upload each episode's audio through a one-time Novamira upload link, then publish it.
# Usage: publish_eps.sh <first_n> <last_n>
S=${0:A:h}
M=$S/payloads/manifest.json
first=$1; last=$2
python3 -I -c "import json,sys; [print(e['n'], e['fname'], e['file'], e['size'], e['payload'], sep='\t') for e in json.load(open(sys.argv[1])) if int(sys.argv[2]) <= e['n'] <= int(sys.argv[3])]" "$M" "$first" "$last" |
while IFS=$'\t' read -r n fname file size payload; do
  echo "== Ep$n $fname"
  printf '{"path":"wp-content/uploads/2026/10/%s","expires_in":1800,"max_bytes":%s,"overwrite":true}' "$fname" "$((size + 1024))" > "$S/up_$n.json"
  R=$(novamira --site theblockopedia.com run novamira/create-upload-link --input @"$S/up_$n.json" --json 2>/dev/null | grep -v "new novamira release")
  URL=$(printf '%s' "$R" | python3 -I -c "import json,sys; d=json.load(sys.stdin).get('data') or {}; print(d.get('upload_url',''))")
  HDR=$(printf '%s' "$R" | python3 -I -c "import json,sys; d=json.load(sys.stdin).get('data') or {}; print(d.get('token_header','X-Novamira-Upload-Token'))")
  TOK=$(printf '%s' "$R" | python3 -I -c "import json,sys; d=json.load(sys.stdin).get('data') or {}; print(d.get('upload_token',''))")
  if [ -z "$URL" ] || [ -z "$TOK" ]; then echo "   upload link failed (file may already exist)"; else
    mkdir -p "$S/upl"; cp "$file" "$S/upl/$fname"
    code=$(curl -s -m 900 -H "$HDR: $TOK" -F "file=@$S/upl/$fname;type=audio/mp4" "$URL" -o "$S/up_res_$n.json" -w "%{http_code}")
    rm -f "$S/upl/$fname"
    echo "   upload http $code, $(python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('bytes_written'), 'bytes')" "$S/up_res_$n.json" 2>/dev/null)"
  fi
  unset TOK
  novamira --site theblockopedia.com run novamira/execute-php --input @"$payload" --yes --json 2>&1 | grep -v "new novamira release" |
    python3 -I -c "import json,sys; d=json.load(sys.stdin); print('   publish:', json.dumps((d.get('data') or {}).get('return_value', d)))"
done
