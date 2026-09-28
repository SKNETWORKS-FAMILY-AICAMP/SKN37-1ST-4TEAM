import csv
import random
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    ElementClickInterceptedException,
)


# ============================================================
# 기본 설정
# ============================================================

URL = "https://www.axa.co.kr/cui/cmk/cu/CMKCUQ01M01.html?"

OUTPUT_FILE = Path.cwd() / "axa_faq.csv"

# True  -> "전체" 탭 제외
# False -> "전체" 탭도 수집
SKIP_ALL_TAB = True

WAIT_TIME = 15

# 무한 스크롤 최대 반복 횟수
MAX_SCROLL_COUNT = 150

# 질문 개수/스크롤 높이가 이 횟수만큼 연속으로 변하지 않으면
# 모든 데이터가 로딩됐다고 판단
STABLE_LIMIT = 5


# ============================================================
# 문자열 정리
# ============================================================

def clean_single_line(text):
    """
    질문, 질문분류처럼 한 줄로 저장할 문자열 정리
    """
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def clean_multiline(text):
    """
    답변의 줄바꿈은 유지하면서 불필요한 공백 제거
    """
    if not text:
        return ""

    lines = []

    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# 랜덤 대기
# ============================================================

def human_sleep(min_sec=0.4, max_sec=0.9):
    time.sleep(random.uniform(min_sec, max_sec))


# ============================================================
# Chrome 설정
# ============================================================

def create_driver():

    options = Options()

    # --------------------------------------------------------
    # 실제 사용자가 보는 브라우저 형태로 실행
    # headless는 자동화 탐지 가능성이 높아질 수 있으므로 사용하지 않음
    # --------------------------------------------------------
    options.add_argument("--start-maximized")
    options.add_argument("--lang=ko-KR")

    # --------------------------------------------------------
    # Selenium 자동화 표시 최소화
    # --------------------------------------------------------
    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"]
    )

    options.add_experimental_option(
        "useAutomationExtension",
        False
    )

    # 알림창 방지
    prefs = {
        "profile.default_content_setting_values.notifications": 2
    }

    options.add_experimental_option(
        "prefs",
        prefs
    )

    driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(40)

    # --------------------------------------------------------
    # navigator.webdriver 제거
    # --------------------------------------------------------
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(
                    navigator,
                    'webdriver',
                    {
                        get: () => undefined
                    }
                );

                Object.defineProperty(
                    navigator,
                    'languages',
                    {
                        get: () => [
                            'ko-KR',
                            'ko',
                            'en-US',
                            'en'
                        ]
                    }
                );
            """
        }
    )

    return driver


# ============================================================
# Element 내부 텍스트 가져오기
# ============================================================

def get_inner_text(driver, element):

    try:
        text = driver.execute_script(
            "return arguments[0].innerText || '';",
            element
        )

        return text or ""

    except Exception:
        try:
            return element.text
        except Exception:
            return ""


# ============================================================
# 보이는 Element만 가져오기
# ============================================================

def get_visible_elements(driver, selector):

    elements = driver.find_elements(
        By.CSS_SELECTOR,
        selector
    )

    result = []

    for element in elements:

        try:
            if element.is_displayed():
                result.append(element)

        except StaleElementReferenceException:
            continue

    return result


# ============================================================
# 질문분류 가져오기
# ============================================================

def get_categories(driver):

    WebDriverWait(driver, WAIT_TIME).until(
        EC.presence_of_all_elements_located(
            (
                By.CSS_SELECTOR,
                "div.cl-tabfolder-item[data-itemidx]"
            )
        )
    )

    human_sleep(1, 1.5)

    tabs = driver.find_elements(
        By.CSS_SELECTOR,
        "div.cl-tabfolder-item[data-itemidx]"
    )

    categories = []
    seen = set()

    for tab in tabs:

        try:

            if not tab.is_displayed():
                continue

            index = tab.get_attribute(
                "data-itemidx"
            )

            text = get_inner_text(
                driver,
                tab
            )

            text = clean_single_line(text)

            # innerText가 비어 있으면 aria-label 사용
            if not text:
                text = clean_single_line(
                    tab.get_attribute(
                        "aria-label"
                    )
                )

            if not text:
                continue

            key = (index, text)

            if key in seen:
                continue

            seen.add(key)

            categories.append(
                {
                    "index": index,
                    "name": text,
                }
            )

        except StaleElementReferenceException:
            continue

    return categories


# ============================================================
# 질문분류 클릭
# ============================================================

def click_category(driver, category):

    index = category["index"]

    selector = (
        f'div.cl-tabfolder-item'
        f'[data-itemidx="{index}"]'
    )

    tabs = driver.find_elements(
        By.CSS_SELECTOR,
        selector
    )

    target = None

    for tab in tabs:

        try:
            if tab.is_displayed():
                target = tab
                break

        except StaleElementReferenceException:
            continue

    if target is None:
        raise RuntimeError(
            f"질문분류 탭을 찾지 못했습니다: "
            f"{category['name']}"
        )

    # 해당 탭으로 이동
    driver.execute_script(
        """
        arguments[0].scrollIntoView({
            behavior:'instant',
            block:'center'
        });
        """,
        target
    )

    human_sleep()

    try:
        target.click()

    except (
        ElementClickInterceptedException,
        StaleElementReferenceException
    ):

        tabs = driver.find_elements(
            By.CSS_SELECTOR,
            selector
        )

        for tab in tabs:

            try:

                if tab.is_displayed():

                    driver.execute_script(
                        "arguments[0].click();",
                        tab
                    )

                    break

            except Exception:
                continue

    human_sleep(1.0, 1.6)


# ============================================================
# 현재 화면의 질문 가져오기
# ============================================================

def get_question_headers(driver):

    return get_visible_elements(
        driver,
        "div.cl-accordion-header"
    )


# ============================================================
# FAQ가 들어 있는 실제 스크롤 영역 찾기
# ============================================================

def find_scroll_container(driver):

    headers = get_question_headers(driver)

    if not headers:

        return driver.execute_script(
            "return document.scrollingElement;"
        )

    first_header = headers[0]

    scroll_element = driver.execute_script(
        """
        let el = arguments[0];

        while (el && el !== document.body) {

            const style = window.getComputedStyle(el);

            const overflowY = style.overflowY;

            if (
                (
                    overflowY === 'auto' ||
                    overflowY === 'scroll'
                ) &&
                el.scrollHeight > el.clientHeight + 30
            ) {
                return el;
            }

            el = el.parentElement;
        }

        return document.scrollingElement;
        """,
        first_header
    )

    return scroll_element


# ============================================================
# 해당 질문분류의 FAQ 끝까지 로딩
# ============================================================

def load_all_questions(driver):

    WebDriverWait(driver, WAIT_TIME).until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                "div.cl-accordion-header"
            )
        ) > 0
    )

    human_sleep(0.8, 1.2)

    scroll_element = find_scroll_container(
        driver
    )

    # 스크롤 영역 시작점으로 이동
    driver.execute_script(
        """
        arguments[0].scrollTop = 0;
        """,
        scroll_element
    )

    human_sleep()

    previous_count = -1
    previous_height = -1

    stable_count = 0

    for scroll_num in range(
        1,
        MAX_SCROLL_COUNT + 1
    ):

        headers = get_question_headers(
            driver
        )

        current_count = len(headers)

        info = driver.execute_script(
            """
            const el = arguments[0];

            return {
                scrollTop: el.scrollTop,
                scrollHeight: el.scrollHeight,
                clientHeight: el.clientHeight
            };
            """,
            scroll_element
        )

        current_height = info[
            "scrollHeight"
        ]

        print(
            f"    스크롤 {scroll_num:03d} | "
            f"현재 질문: {current_count}개 | "
            f"높이: {current_height}"
        )

        # ------------------------------------------
        # 이전 상태와 비교
        # ------------------------------------------

        if (
            current_count == previous_count
            and
            current_height == previous_height
        ):
            stable_count += 1

        else:
            stable_count = 0

        previous_count = current_count
        previous_height = current_height

        # ------------------------------------------
        # 스크롤 끝 확인
        # ------------------------------------------

        at_bottom = (
            info["scrollTop"]
            +
            info["clientHeight"]
            >=
            info["scrollHeight"] - 20
        )

        if (
            at_bottom
            and
            stable_count >= STABLE_LIMIT
        ):

            print(
                f"    → 추가 FAQ 없음. "
                f"총 {current_count}개"
            )

            break

        # ------------------------------------------
        # 자연스럽게 아래로 이동
        # ------------------------------------------

        scroll_amount = max(
            int(
                info["clientHeight"]
                * random.uniform(
                    0.65,
                    0.9
                )
            ),
            400
        )

        driver.execute_script(
            """
            const el = arguments[0];
            const amount = arguments[1];

            el.scrollTop =
                Math.min(
                    el.scrollTop + amount,
                    el.scrollHeight
                );
            """,
            scroll_element,
            scroll_amount
        )

        # AJAX / IntersectionObserver 대기
        human_sleep(
            0.7,
            1.15
        )

    # 마지막 AJAX 로딩 대기
    human_sleep(
        1.2,
        1.8
    )

    headers = get_question_headers(
        driver
    )

    return len(headers)


# ============================================================
# 질문에 연결된 답변 Element 찾기
# ============================================================

def find_answer_element(driver, header):

    # --------------------------------------------------------
    # 방법 1
    # 질문의 aria-controls와 답변 id 연결
    #
    # 네가 올린 DOM 화면:
    #
    # aria-controls="tb1-31g"
    #
    # 형태를 우선 사용
    # --------------------------------------------------------

    try:

        content_id = header.get_attribute(
            "aria-controls"
        )

        if content_id:

            elements = driver.find_elements(
                By.ID,
                content_id
            )

            if elements:
                return elements[0]

    except Exception:
        pass

    # --------------------------------------------------------
    # 방법 2
    # 같은 부모 안의 cl-accordion-content 검색
    # --------------------------------------------------------

    try:

        element = driver.execute_script(
            """
            let header = arguments[0];

            let parent = header.parentElement;

            for (let i = 0; i < 8; i++) {

                if (!parent) {
                    break;
                }

                let content =
                    parent.querySelector(
                        '.cl-accordion-content'
                    );

                if (content) {
                    return content;
                }

                parent =
                    parent.parentElement;
            }

            return null;
            """,
            header
        )

        if element:
            return element

    except Exception:
        pass

    # --------------------------------------------------------
    # 방법 3
    # 질문 바로 뒤에서 답변 검색
    # --------------------------------------------------------

    try:

        return header.find_element(
            By.XPATH,
            (
                "./following::*"
                "[contains("
                "concat(' ', normalize-space(@class), ' '), "
                "' cl-accordion-content '"
                ")][1]"
            )
        )

    except Exception:
        return None


# ============================================================
# 질문 열기
# ============================================================

def open_question(driver, header):

    expanded = (
        header.get_attribute(
            "aria-expanded"
        )
        or ""
    ).lower()

    if expanded == "true":
        return

    driver.execute_script(
        """
        arguments[0].scrollIntoView({
            behavior:'instant',
            block:'center'
        });
        """,
        header
    )

    human_sleep(
        0.15,
        0.35
    )

    try:

        header.click()

    except Exception:

        driver.execute_script(
            "arguments[0].click();",
            header
        )

    # 애니메이션 및 답변 렌더링 시간
    human_sleep(
        0.25,
        0.5
    )


# ============================================================
# 질문 텍스트 정리
# ============================================================

def get_question_text(
    driver,
    header,
    category_name
):

    question = get_inner_text(
        driver,
        header
    )

    question = clean_single_line(
        question
    )

    if not question:

        question = clean_single_line(
            header.get_attribute(
                "aria-label"
            )
        )

    # 일부 AXA accordion에서는
    # 질문 앞쪽에 질문분류가 같이 들어올 수 있음
    if category_name:

        if question.startswith(
            category_name + " "
        ):
            question = question[
                len(category_name):
            ].strip()

    return question


# ============================================================
# 현재 질문분류 FAQ 수집
# ============================================================

def scrape_category(
    driver,
    category_name
):

    rows = []

    total = len(
        get_question_headers(
            driver
        )
    )

    print(
        f"    추출 시작: "
        f"{total}개"
    )

    for i in range(total):

        try:

            # 클릭할 때 DOM 상태가 변할 수 있으므로
            # 매번 다시 Element 목록 가져오기
            headers = get_question_headers(
                driver
            )

            if i >= len(headers):
                break

            header = headers[i]

            question = get_question_text(
                driver,
                header,
                category_name
            )

            print(
                f"      "
                f"[{i + 1}/{total}] "
                f"{question[:60]}"
            )

            # 질문 열기
            open_question(
                driver,
                header
            )

            # 클릭 후 header가 stale될 가능성이 있으므로
            # 다시 목록 획득
            headers = get_question_headers(
                driver
            )

            if i < len(headers):
                header = headers[i]

            answer_element = find_answer_element(
                driver,
                header
            )

            answer = ""

            if answer_element:

                # 답변 내용이 렌더링될 때까지 잠깐 대기
                for _ in range(10):

                    raw_answer = get_inner_text(
                        driver,
                        answer_element
                    )

                    answer = clean_multiline(
                        raw_answer
                    )

                    if answer:
                        break

                    time.sleep(0.2)

            rows.append(
                {
                    "질문분류": category_name,
                    "질문": question,
                    "답변": answer,
                }
            )

        except StaleElementReferenceException:

            print(
                "        DOM 갱신 감지 → 재시도"
            )

            human_sleep()

            continue

        except Exception as e:

            print(
                f"        오류: {e}"
            )

            rows.append(
                {
                    "질문분류": category_name,
                    "질문": "",
                    "답변": "",
                }
            )

    return rows


# ============================================================
# 중복 제거
# ============================================================

def remove_duplicates(rows):

    result = []

    seen = set()

    for row in rows:

        key = (
            row["질문분류"],
            row["질문"],
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(row)

    return result


# ============================================================
# CSV 저장
# ============================================================

def save_csv(rows):

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "질문분류",
                "질문",
                "답변",
            ]
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    print()
    print(
        "=" * 60
    )

    print(
        f"CSV 저장 완료"
    )

    print(
        f"파일 위치: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"총 데이터: "
        f"{len(rows)}개"
    )

    print(
        "=" * 60
    )


# ============================================================
# 메인
# ============================================================

def main():

    driver = create_driver()

    all_rows = []

    try:

        print(
            "AXA FAQ 페이지 접속 중..."
        )

        driver.get(URL)

        WebDriverWait(
            driver,
            WAIT_TIME
        ).until(
            EC.presence_of_element_located(
                (
                    By.TAG_NAME,
                    "body"
                )
            )
        )

        human_sleep(
            2,
            3
        )

        # ----------------------------------------
        # 질문분류 조회
        # ----------------------------------------

        categories = get_categories(
            driver
        )

        print()
        print(
            "발견된 질문분류"
        )

        for category in categories:

            print(
                f"  "
                f"data-itemidx="
                f"{category['index']} | "
                f"{category['name']}"
            )

        print()

        # ----------------------------------------
        # 질문분류별 반복
        # ----------------------------------------

        for num, category in enumerate(
            categories,
            start=1
        ):

            category_name = category[
                "name"
            ]

            # "전체" 제외
            if (
                SKIP_ALL_TAB
                and
                clean_single_line(
                    category_name
                ) == "전체"
            ):

                print(
                    "전체 탭은 "
                    "중복 방지를 위해 건너뜁니다."
                )

                continue

            print()
            print(
                "=" * 60
            )

            print(
                f"[{num}/{len(categories)}] "
                f"{category_name}"
            )

            print(
                "=" * 60
            )

            # 질문분류 클릭
            click_category(
                driver,
                category
            )

            # 해당 분류의 모든 질문 로딩
            question_count = (
                load_all_questions(
                    driver
                )
            )

            print(
                f"    최종 로딩 질문 수: "
                f"{question_count}"
            )

            # 질문 + 답변 추출
            rows = scrape_category(
                driver,
                category_name
            )

            all_rows.extend(
                rows
            )

            print(
                f"    추출 완료: "
                f"{len(rows)}개"
            )

            # 질문분류 전환 간 과도한 요청 방지
            human_sleep(
                1.2,
                2.2
            )

        # ----------------------------------------
        # 중복 제거
        # ----------------------------------------

        all_rows = remove_duplicates(
            all_rows
        )

        # ----------------------------------------
        # CSV 저장
        # ----------------------------------------

        save_csv(
            all_rows
        )

    except Exception as e:

        print()
        print(
            "크롤링 도중 오류 발생"
        )

        print(
            repr(e)
        )

        # 디버깅용 화면/HTML 저장
        try:

            driver.save_screenshot(
                "axa_error.png"
            )

            Path(
                "axa_error.html"
            ).write_text(
                driver.page_source,
                encoding="utf-8"
            )

            print(
                "디버깅용 파일 저장:"
            )

            print(
                "  axa_error.png"
            )

            print(
                "  axa_error.html"
            )

        except Exception:
            pass

        raise

    finally:

        # 바로 닫히는 것이 싫다면 아래 sleep을
        # time.sleep(10) 등으로 변경 가능
        human_sleep(
            1,
            1.5
        )

        driver.quit()


if __name__ == "__main__":
    main()
