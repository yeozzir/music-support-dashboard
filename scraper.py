"""
scraper.py — 음악 아티스트 지원사업 수집기

이 스크립트는 grounz.net과 다른 사이트들을 방문해서
지원사업 공고를 수집하고 programs.json에 저장합니다.

실행 방법:
  python3 scraper.py

필요한 라이브러리 설치 (처음 한 번만):
  pip3 install requests beautifulsoup4
"""

import json
import datetime
import os
import time

# requests: 웹 페이지를 다운로드하는 라이브러리
# BeautifulSoup: HTML에서 원하는 정보를 골라내는 라이브러리
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("=" * 50)
    print("필요한 라이브러리가 없습니다.")
    print("아래 명령어로 설치해주세요:")
    print("  pip3 install requests beautifulsoup4")
    print("=" * 50)
    exit(1)

# ── 설정 ──────────────────────────────────────────
# 이 스크립트 파일이 있는 폴더를 기준으로 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "programs.json")
LOG_PATH = os.path.join(BASE_DIR, "logs", "scraper.log")

# 웹 요청 시 사용할 헤더 (브라우저처럼 보이게 해서 차단 방지)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# ── 로그 기록 함수 ────────────────────────────────
def log(message):
    """로그를 터미널과 파일 양쪽에 출력합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)

    # logs 폴더가 없으면 만들기
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ── 기존 programs.json 불러오기 ───────────────────
def load_existing_programs():
    """
    기존 programs.json을 읽어서 반환합니다.
    파일이 없으면 빈 구조를 반환합니다.
    """
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": "", "programs": []}


# ── 기존 프로그램 ID 목록 가져오기 ────────────────
def get_existing_ids(data):
    """이미 저장된 지원사업 ID 목록을 반환합니다. 중복 추가 방지에 사용."""
    return {p["id"] for p in data.get("programs", [])}


# ── grounz.net 수집 ───────────────────────────────
def scrape_grounz():
    """
    grounz.net/announcement 에서 공고 목록을 수집합니다.

    주의: grounz.net은 JavaScript로 동작하는 사이트라서
    requests만으로는 실제 공고 목록을 가져오기 어렵습니다.
    현재는 페이지 접근 가능 여부만 확인하고,
    실제 공고는 수동으로 추가하거나 향후 Playwright로 업그레이드 예정입니다.

    반환: 빈 리스트 (수동 추가 안내)
    """
    url = "https://grounz.net/announcement?category=0"
    log(f"grounz.net 확인 중: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            log("grounz.net: 사이트 접근 가능 — JavaScript 렌더링 사이트라 자동 수집 불가")
            log("grounz.net: https://grounz.net/announcement 에서 직접 확인 후 수동 추가 권장")
        else:
            log(f"grounz.net: 응답 코드 {response.status_code}")
    except Exception as e:
        log(f"grounz.net: 접근 실패 — {e}")

    return []


# ── 한국예술인복지재단 (KAWF) 수집 ───────────────
def scrape_kawf():
    """
    한국예술인복지재단 공지사항에서 [공고] 항목을 수집합니다.
    URL: https://www.kawf.kr/notice/sub01.do

    이 사이트는 JavaScript 방식이라 링크를 직접 가져올 수 없습니다.
    제목만 추출하고, 링크는 공지사항 메인 페이지로 연결합니다.

    반환: 수집된 프로그램 딕셔너리 리스트
    """
    url = "https://www.kawf.kr/notice/sub01.do"
    log(f"한국예술인복지재단 수집 시작: {url}")
    new_programs = []

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")

        # 공지사항 목록 링크 찾기
        links = soup.select("ul li a")

        if not links:
            log("한국예술인복지재단: 공고 목록을 찾지 못했습니다.")
            return []

        log(f"한국예술인복지재단: {len(links)}개 항목 발견")

        import re
        import hashlib

        # 제목에 이 키워드가 포함되면 수집에서 제외 (생활지원금, 행정성 공고 등)
        EXCLUDE_KEYWORDS = [
            "예술활동준비금",   # 생활 지원금 성격
            "생활안정자금",     # 생활 지원금
            "융자",             # 대출성 지원
            "채용",             # 직원 채용 공고
            "합격자",           # 채용 관련
            "입찰",             # 용역 입찰
            "용역",             # 시스템/연구 용역
            "자녀돌봄",         # 복지 지원
            "성희롱",           # 교육 안내
            "방지교육",         # 교육 안내
        ]

        for link_el in links:
            try:
                title = link_el.get_text(strip=True)

                # "[공고]" 태그가 붙은 항목만 수집 (채용, 안내 제외)
                if not title.startswith("[공고]"):
                    continue

                # 제외 키워드가 포함된 항목 스킵
                if any(kw in title for kw in EXCLUDE_KEYWORDS):
                    log(f"  제외: {title[:50]}")
                    continue

                # 제목에서 "[공고]" 태그 제거 후 정리
                clean_title = title.replace("[공고]", "").strip()

                if len(clean_title) < 3:
                    continue

                # 고유 ID: 제목의 해시 앞 8자리 사용
                unique_id = hashlib.md5(clean_title.encode()).hexdigest()[:8]
                program_id = f"kawf-{unique_id}"

                new_programs.append({
                    "id": program_id,
                    "name": clean_title[:80],
                    "organization": "한국예술인복지재단",
                    "deadline": "공고 참조",
                    "amount": "공고 참조",
                    "target": "공고 페이지에서 확인",
                    "url": url,  # 상세 링크 없으므로 목록 페이지로 연결
                    "source": "kawf",
                    "urgent": False,
                })

            except Exception as e:
                log(f"한국예술인복지재단 항목 파싱 오류: {e}")
                continue

        log(f"한국예술인복지재단: {len(new_programs)}개 [공고] 수집 완료")
        return new_programs

    except Exception as e:
        log(f"한국예술인복지재단: 수집 실패 — {e}")
        return []


# ── HTML에서 지원 조건/내용 추출 (공통 함수) ────────
def _parse_summary_from_html(html):
    """
    BeautifulSoup으로 파싱한 HTML에서 지원 조건과 지원 내용을 추출합니다.
    fetch_summary와 fetch_summary_playwright 양쪽에서 공통으로 사용합니다.
    """
    import re

    CONDITION_KEYWORDS = [
        "지원대상", "지원 대상", "신청대상", "신청자격", "지원조건",
        "모집대상", "모집 대상", "참가자격", "신청기간", "접수기간",
        "모집기간", "신청 기간", "접수 기간",
    ]
    CONTENT_KEYWORDS = [
        "지원내용", "지원 내용", "지원금액", "지원 금액", "지원규모",
        "지원사항", "혜택", "선정혜택", "지원혜택", "지원금",
        "지원 규모", "사업내용", "사업 내용",
    ]

    def clean(text):
        return re.sub(r"\s+", " ", text).strip()

    def is_junk(text):
        if len(text) < 5:
            return True
        junk_patterns = [
            r"로그인|회원가입|마이페이지|사이트맵|즐겨찾기",
            r"바로가기|레이어닫기|레이어 닫기",
            r"^\s*[A-Za-z0-9_\-\.]+\s*$",
        ]
        for pat in junk_patterns:
            if re.search(pat, text):
                return True
        return False

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
        tag.decompose()

    result = {"조건": "", "내용": ""}

    # 방법 1: 테이블 th→td 쌍
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        label = clean(cells[0].get_text())
        value = clean(cells[1].get_text())
        if not value or is_junk(value):
            continue
        for kw in CONDITION_KEYWORDS:
            if kw in label and not result["조건"]:
                result["조건"] = value[:150]
                break
        for kw in CONTENT_KEYWORDS:
            if kw in label and not result["내용"]:
                result["내용"] = value[:150]
                break
        if result["조건"] and result["내용"]:
            break

    # 방법 2: 정의목록 dt→dd 쌍
    if not result["조건"] or not result["내용"]:
        for dl in soup.find_all("dl"):
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                label = clean(dt.get_text())
                value = clean(dd.get_text())
                if not value or is_junk(value):
                    continue
                for kw in CONDITION_KEYWORDS:
                    if kw in label and not result["조건"]:
                        result["조건"] = value[:150]
                        break
                for kw in CONTENT_KEYWORDS:
                    if kw in label and not result["내용"]:
                        result["내용"] = value[:150]
                        break

    # 방법 3: 줄 단위 스캔
    if not result["조건"] or not result["내용"]:
        lines = soup.get_text(separator="\n").splitlines()
        for i, line in enumerate(lines):
            line = clean(line)
            if not line:
                continue
            kv_match = re.match(r"^(.{2,12})[：:·]\s*(.+)$", line)
            if kv_match:
                label, value = kv_match.group(1), clean(kv_match.group(2))
                if not is_junk(value):
                    for kw in CONDITION_KEYWORDS:
                        if kw in label and not result["조건"]:
                            result["조건"] = value[:150]
                    for kw in CONTENT_KEYWORDS:
                        if kw in label and not result["내용"]:
                            result["내용"] = value[:150]
                continue
            for kw in CONDITION_KEYWORDS:
                if line.strip() == kw and i + 1 < len(lines):
                    nxt = clean(lines[i + 1])
                    if nxt and not is_junk(nxt) and not result["조건"]:
                        result["조건"] = nxt[:150]
            for kw in CONTENT_KEYWORDS:
                if line.strip() == kw and i + 1 < len(lines):
                    nxt = clean(lines[i + 1])
                    if nxt and not is_junk(nxt) and not result["내용"]:
                        result["내용"] = nxt[:150]
            if result["조건"] and result["내용"]:
                break

    return result


# ── 개별 공고 페이지에서 요약 추출 (일반 방식) ──────
def fetch_summary(url):
    """
    requests로 HTML을 받아서 요약을 추출합니다.
    JS 렌더링이 필요 없는 사이트에 사용합니다.
    JS 사이트는 fetch_summary_playwright()를 사용하세요.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        response.encoding = "utf-8"
        return _parse_summary_from_html(response.text)
    except requests.exceptions.Timeout:
        log(f"  요약 시간 초과: {url[:50]}")
    except Exception:
        pass
    return {"조건": "", "내용": ""}


# ── 개별 공고 페이지에서 요약 추출 (Playwright 방식) ─
def fetch_summary_playwright(url):
    """
    실제 크롬 브라우저를 열어서 JS가 렌더링된 뒤의 HTML을 읽습니다.
    서울문화재단, ARKO, KAWF 등 JS 사이트에 사용합니다.
    일반 방식보다 느리지만(3~5초) JS로 만들어지는 내용도 읽을 수 있습니다.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # headless=True: 브라우저 창이 화면에 안 보이게 백그라운드로 실행
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # 실제 사용자처럼 보이도록 User-Agent 설정
            page.set_extra_http_headers({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            })
            # domcontentloaded: JS 실행 전 기본 HTML이 로드되면 진행
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # JS가 화면을 그릴 때까지 3초 추가 대기
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
        return _parse_summary_from_html(html)
    except Exception as e:
        log(f"  Playwright 실패: {url[:50]} ({e})")
    return {"조건": "", "내용": ""}


# ── 만료된 프로그램 제거 ─────────────────────────
def remove_expired_programs(programs):
    """
    마감일이 지난 프로그램을 목록에서 제거합니다.
    - YYYY-MM-DD 형식의 마감일이 오늘 이전이면 제거
    - 이름에 2020~2023년이 포함된 경우 제거
    - 이름에 2025년이 포함된 경우 제거 (2026년 기준)
    - 요약의 조건에 과거 날짜 범위가 있으면 제거
    """
    import re

    today = datetime.date.today()
    kept = []
    removed = 0

    for p in programs:
        name = p.get("name", "")
        deadline = p.get("deadline", "")
        summary = p.get("summary", {})
        cond = summary.get("조건", "") if isinstance(summary, dict) else ""

        expired = False

        # 1. 마감일이 YYYY-MM-DD 형식이고 오늘 이전
        if re.match(r"^\d{4}-\d{2}-\d{2}$", deadline):
            dl = datetime.date.fromisoformat(deadline)
            if dl < today:
                expired = True

        # 2. 이름에 명백히 과거 연도 포함 (2020~2023, 2025)
        if not expired:
            current_year = today.year
            for year in range(2020, current_year):  # 작년까지 전부 제거
                if str(year) in name:
                    expired = True
                    break

        # 3. 조건에 과거 날짜 포함
        if not expired and cond:
            for year in range(2020, current_year):
                if f"{year}." in cond or f"{year}년" in cond:
                    expired = True
                    break

        # 4. 조건에 날짜 범위가 있고 종료일이 오늘 이전
        if not expired and cond:
            # "~ YYYY.MM.DD" 형식
            m = re.search(r"~\s*(\d{4})\.(\d{2})\.(\d{2})", cond)
            if m:
                end = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if end < today:
                    expired = True
            # "~ MM월 DD일" 형식
            if not expired:
                m = re.search(r"~\s*(\d+)월\s*(\d+)일", cond)
                if m:
                    year_m = re.search(r"(20\d{2})년", cond)
                    yr = int(year_m.group(1)) if year_m else today.year
                    end = datetime.date(yr, int(m.group(1)), int(m.group(2)))
                    if end < today:
                        expired = True
            # "YYYY 년 MM 월 DD 일 ... 마감" 형식 (공백 포함)
            if not expired:
                m = re.search(r"(\d{4})\s*년\s*(\d+)\s*월\s*(\d+)\s*일.*마감", cond)
                if m:
                    end = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if end < today:
                        expired = True

        if expired:
            removed += 1
        else:
            kept.append(p)

    if removed > 0:
        log(f"만료된 프로그램 {removed}개 제거")
    return kept


# ── programs.json 저장 ────────────────────────────
def save_programs(data):
    """
    수집 결과를 programs.json에 저장합니다.
    저장 전에 백업 파일(programs.json.bak)을 만들어둡니다.
    """
    # 기존 파일 백업
    if os.path.exists(JSON_PATH):
        backup_path = JSON_PATH + ".bak"
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            backup_content = f.read()
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(backup_content)
        log(f"기존 파일 백업: {backup_path}")

    # 새 데이터 저장
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log(f"programs.json 저장 완료: {JSON_PATH}")


# ── 네이버 웹 검색으로 새 출처 발견 ──────────────
def search_naver(query):
    """
    네이버 웹 검색 결과에서 음악 지원사업 공고 링크를 찾습니다.
    API 키 없이 검색 결과 HTML을 직접 파싱합니다.

    query: 검색어 (예: "음악 지원사업 공고 2026")
    반환: (제목, URL) 튜플 리스트
    """
    import urllib.parse
    import re

    encoded_query = urllib.parse.quote(query)
    url = f"https://search.naver.com/search.naver?where=web&query={encoded_query}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            # 외부 URL만 (네이버 내부 제외)
            if not href.startswith("http") or "naver.com" in href:
                continue

            # 텍스트 길이 10~100자 사이, URL 형태가 아닌 것
            if not (10 <= len(text) <= 100):
                continue
            if re.search(r"www\.|\.kr|\.com|\.go", text):
                continue

            # URL 중복 제거
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # 제목 앞의 경로 형태 접두어 제거 (예: "문화사업>지원사업안내 >지원사업 공고-")
            clean_title = re.sub(r"^[가-힣\s>·]+공고[-\s]*", "", text).strip()
            if not clean_title:
                clean_title = text

            results.append((clean_title, href))

        return results

    except Exception as e:
        log(f"네이버 검색 실패 ({query}): {e}")
        return []


def search_web_for_programs():
    """
    웹 검색을 통해 기존에 없는 음악 지원사업 공고를 새로 발견합니다.

    검색어를 여러 개 사용해서 다양한 공고를 찾고,
    관련성 높은 결과만 필터링해서 반환합니다.

    반환: 수집된 프로그램 딕셔너리 리스트
    """
    import re
    import hashlib

    # 매주 다양한 공고를 찾기 위한 검색어 목록
    # 올해 연도를 자동으로 포함
    year = datetime.date.today().year
    queries = [
        f"음악 창작 지원사업 공고 {year}",
        f"뮤지션 지원금 공모 {year}",
        f"인디 음악 지원 공모전 {year}",
        f"음악인 창작활동 지원 공고 {year}",
        f"밴드 공연 지원 공모 {year}",
    ]

    # 제목에 이 키워드 중 하나라도 있어야 관련 있는 공고로 판단
    INCLUDE_KEYWORDS = [
        "음악", "뮤직", "뮤지션", "밴드", "아티스트", "창작",
        "인디", "앨범", "레코딩", "음반", "작곡", "싱어송라이터",
    ]

    # 제목에 이 키워드가 있으면 무조건 제외
    EXCLUDE_KEYWORDS = [
        "생활안정", "융자", "채용", "입찰", "용역", "돌봄",
        "성희롱", "교육", "세미나", "포럼", "토론회",
        "연구용역", "시스템 구축", "유지보수",
        "선정결과", "합격자", "심의일정", "심의 일정",
        "보도자료", "press", "뉴스", "기사",  # 뉴스/보도 기사 제외
        "오디션", "audition",                 # 오디션 (지원사업 아님)
        "콘테스트", "contest", "경연",        # 경연대회 (지원사업 아님)
        "전통", "국악", "무형유산", "민요",   # 전통예술 (범위 외)
        "무용", "연극", "뮤지컬", "미술",     # 타 예술 장르
        "공연장상주", "단체육성",             # 단체 대상 사업
    ]

    # 신뢰할 수 있는 도메인 (공공기관, 재단, 문화 관련)
    TRUSTED_DOMAINS = [
        "arko.or.kr", "sfac.or.kr", "kawf.kr",   # 주요 예술 기관
        "kocca.kr",                                # 콘텐츠 기관
        "sangsangmadang.com", "grounz.net",        # 음악 플랫폼
        "ebs.co.kr",                               # EBS
        "bizinfo.go.kr",                           # 정부 지원사업 포털
    ]

    log("웹 검색으로 새 출처 탐색 시작")
    found = {}  # URL 기준 중복 방지

    for query in queries:
        log(f"  검색: {query}")
        results = search_naver(query)
        log(f"  → {len(results)}개 결과")

        for title, url in results:
            # 이미 찾은 URL은 스킵
            if url in found:
                continue

            # 신뢰 도메인 또는 제목에 음악 키워드 포함 여부
            is_trusted = any(domain in url for domain in TRUSTED_DOMAINS)
            has_keyword = any(kw in title for kw in INCLUDE_KEYWORDS)
            is_excluded = any(kw in title for kw in EXCLUDE_KEYWORDS)

            # 현재 연도가 제목에 없으면 제외 (오래된 공고 방지)
            has_year = str(year) in title

            if (is_trusted or (has_keyword and has_year)) and not is_excluded:
                found[url] = title

        time.sleep(1)  # 검색 간 1초 대기 (서버 부담 방지)

    if not found:
        log("웹 검색: 새로운 공고를 찾지 못했습니다.")
        return []

    log(f"웹 검색: 후보 {len(found)}개 발견 → 프로그램으로 등록")

    new_programs = []
    for url, title in found.items():
        # 제목에서 고유 ID 생성
        unique_id = hashlib.md5(url.encode()).hexdigest()[:8]
        program_id = f"web-{unique_id}"

        new_programs.append({
            "id": program_id,
            "name": title[:80],
            "organization": "웹 검색 발견",
            "deadline": "공고 참조",
            "amount": "공고 참조",
            "target": "공고 페이지에서 확인",
            "url": url,
            "source": "web-search",
            "urgent": False,
        })

    return new_programs


# ── 메인 실행 ─────────────────────────────────────
def main():
    log("=" * 50)
    log("음악 아티스트 지원사업 수집 시작")
    log("=" * 50)

    # 1. 기존 데이터 불러오기
    data = load_existing_programs()
    existing_ids = get_existing_ids(data)
    original_count = len(data["programs"])
    log(f"기존 데이터: {original_count}개")

    # 2. 각 사이트에서 수집 (사이트 간 1초 대기)
    all_new = []

    grounz_programs = scrape_grounz()
    all_new.extend(grounz_programs)
    time.sleep(1)

    kawf_programs = scrape_kawf()
    all_new.extend(kawf_programs)
    time.sleep(1)

    # 3. 웹 검색으로 새 출처 발견
    web_programs = search_web_for_programs()
    all_new.extend(web_programs)

    # 4. 중복 제거 후 기존 데이터에 추가
    added = 0
    for program in all_new:
        if program["id"] not in existing_ids:
            data["programs"].append(program)
            existing_ids.add(program["id"])
            added += 1

    # 5. 요약이 없는 프로그램에 요약 추가
    # summary가 dict 형식이고 조건·내용이 있으면 재수집 안 함
    need_summary = [
        p for p in data["programs"]
        if not isinstance(p.get("summary"), dict)
        or not (p["summary"].get("조건") or p["summary"].get("내용"))
    ]

    # JS 렌더링이 필요한 사이트 도메인 목록
    # 이 사이트들은 Playwright(실제 브라우저)로 읽어야 내용이 보임
    JS_SITES = [
        "sfac.or.kr",       # 서울문화재단
        "arko.or.kr",       # 한국문화예술위원회
        "kawf.kr",          # 한국예술인복지재단
        "ifac.or.kr",       # 인천문화재단
        "swcf.or.kr",       # 수원문화재단
        "kocca.kr",         # 한국콘텐츠진흥원
        "artnuri.or.kr",    # 아트누리
    ]

    if need_summary:
        log(f"요약 수집 시작: {len(need_summary)}개 프로그램")
        for i, program in enumerate(need_summary, 1):
            url = program["url"]
            log(f"  [{i}/{len(need_summary)}] {program['name'][:40]}")

            # JS 사이트이면 Playwright, 아니면 일반 방식 사용
            use_playwright = any(domain in url for domain in JS_SITES)
            if use_playwright:
                log(f"    → Playwright(브라우저) 방식 사용")
                summary = fetch_summary_playwright(url)
            else:
                summary = fetch_summary(url)

            program["summary"] = summary
            time.sleep(0.5)  # 서버 부담 방지
        log("요약 수집 완료")

    # 6. 만료된 프로그램 제거
    before_count = len(data["programs"])
    data["programs"] = remove_expired_programs(data["programs"])
    expired_count = before_count - len(data["programs"])

    # 7. 업데이트 날짜 갱신
    data["updated_at"] = datetime.date.today().strftime("%Y-%m-%d")

    # 8. 저장
    save_programs(data)

    # 9. 결과 요약
    log("=" * 50)
    log(f"수집 완료!")
    log(f"  기존: {original_count}개")
    log(f"  새로 추가: {added}개")
    log(f"  만료 제거: {expired_count}개")
    log(f"  전체: {len(data['programs'])}개")
    log("=" * 50)


# 이 파일을 직접 실행할 때만 main() 호출
if __name__ == "__main__":
    main()
