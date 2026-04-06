#!/bin/bash
# run.sh — 스크래퍼 실행 + 로그 기록 스크립트
#
# 이 파일은 crontab이 매주 자동으로 실행합니다.
# 직접 실행하고 싶으면 터미널에서:
#   bash ~/music-support-dashboard/run.sh

# 이 스크립트가 있는 폴더로 이동
cd "$(dirname "$0")"

# logs 폴더가 없으면 만들기
mkdir -p logs

# 파이썬 스크래퍼 실행
# python3 명령어를 찾을 수 없을 경우를 대비해 경로 지정
/usr/bin/python3 scraper.py

# 실행 결과를 종료 코드로 확인
if [ $? -eq 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] run.sh: 스크래퍼 성공적으로 완료" >> logs/scraper.log
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] run.sh: 스크래퍼 실행 중 오류 발생" >> logs/scraper.log
fi
