#!/usr/bin/env bash
# Build demo/interviewlens-demo.mp4 from the real Playwright screenshots.
# Narration: espeak-ng synthetic voice. Subtitles burned in from the same text.
set -euo pipefail
cd "$(dirname "$0")"
SHOTS=screenshots
WORK=/tmp/interviewlens-video
mkdir -p "$WORK"

# segments: "image|narration text"
SEGMENTS=(
"01-home.png|InterviewLens is an AI-powered, role-based candidate screening system. You upload a resume, pick a role, and it generates interview questions using retrieval over machine learning textbooks."
"02-upload-selected.png|Here, we upload a real resume, a P D F, and select the A I M L Engineer role. The knowledge base for this role is four textbooks: Mitchell, Burkov, Bishop, and Brownlee."
"03-generating.png|Starting the interview parses the resume, extracts skills, retrieves relevant textbook passages, and generates five questions with a local model. On this machine, that took about thirty seconds."
"04-question-1.png|Question one, on supervised learning: What is the supervised learning theory about? Every question shows its source. This one is grounded in Bishop's Pattern Recognition and Machine Learning."
"05-question-1-answered.png|We type an answer in the box and submit it. The answer is saved, and the interview moves on to the next question."
"06-question-2.png|Question two, on decision trees, comes from Burkov's The Hundred-Page Machine Learning Book."
"05-question-2-answered.png|We answer it the same way: type the answer, submit, and the next question appears."
"05-question-3-answered.png|Question three asks about the learning rate of neural networks. Again, the answer is typed and submitted in the app."
"06-question-4.png|Question four covers model evaluation, grounded in Mitchell's Machine Learning."
"05-question-5-answered.png|The fifth and final question is submitted, which finishes the interview and generates the summary."
"07-summary.png|The summary shows five of five questions answered, the topics covered, and strengths and gaps. These are basic heuristics from answer length and keyword overlap, not scores, and not a hiring decision."
"08-summary-qa.png|Below the summary is the full question-and-answer record, with every question traced back to its textbook source. That is InterviewLens: resume in, grounded interview out."
)

# 1. Generate one wav per segment, measure durations.
: > "$WORK/concat_video.txt"
: > "$WORK/concat_audio.txt"
cat > "$WORK/subs.ass" <<'ASS'
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,26,&HFFFFFF,&HFFFFFF,&H000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,120,120,36,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
ASS
t=0
i=0
for seg in "${SEGMENTS[@]}"; do
  img="${seg%%|*}"
  text="${seg#*|}"
  i=$((i+1))
  wav="$WORK/nar$i.wav"
  espeak-ng -v en -s 145 -p 40 -w "$wav" "$text"
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$wav")
  # segment shows at least 8s, or audio length + 2s breathing room
  segdur=$(python3 -c "print(max(8.0, float('$dur') + 2.0))")
  echo "file '$PWD/$SHOTS/$img'" >> "$WORK/concat_video.txt"
  echo "duration $segdur" >> "$WORK/concat_video.txt"
  echo "file '$wav'" >> "$WORK/concat_audio.txt"
  # ASS entry (PlayRes 1920x1080, so Fontsize is in real pixels)
  start_ts=$(python3 -c "s=$t; print(f'{int(s//3600)}:{int(s//60)%60:02d}:{s%60:05.2f}')")
  end_ts=$(python3 -c "s=$t + $segdur; print(f'{int(s//3600)}:{int(s//60)%60:02d}:{s%60:05.2f}')")
  echo "Dialogue: 0,${start_ts},${end_ts},Default,,0,0,0,,${text}" >> "$WORK/subs.ass"
  t=$(python3 -c "print($t + $segdur)")
  echo "seg $i $img dur=${segdur}s audio=${dur}s"
done
# concat demuxer needs the last file repeated (no duration on last entry otherwise)
last_img="${SEGMENTS[-1]%%|*}"
echo "file '$PWD/$SHOTS/$last_img'" >> "$WORK/concat_video.txt"

# 2. Silent slideshow video, 1920x1080, 30fps.
ffmpeg -y -v error -f concat -safe 0 -i "$WORK/concat_video.txt" \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" \
  -r 30 -c:v libx264 -crf 20 -preset medium "$WORK/silent.mp4"

# 3. Concatenate narration audio.
ffmpeg -y -v error -f concat -safe 0 -i "$WORK/concat_audio.txt" -c:a pcm_s16le "$WORK/narration.wav"

# 4. Mux audio + burn subtitles.
ffmpeg -y -v error -i "$WORK/silent.mp4" -i "$WORK/narration.wav" \
  -vf "ass=$WORK/subs.ass" \
  -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -shortest \
  interviewlens-demo.mp4

ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,codec_name \
  -of default=noprint_wrappers=1 interviewlens-demo.mp4
ls -la interviewlens-demo.mp4
