import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def create_stealth_driver():
    """강력한 봇 탐지 우회 옵션이 적용된 Selenium Chrome Driver를 생성합니다."""
    options = Options()

    # 1. 자동화 감지 플래그 제거
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # 2. 실제 브라우저 User-Agent 설정 및 크기 지정
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)

    # 3. CDP 명령을 이용해 navigator.webdriver 변수 조작 우회
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        },
    )
    return driver


def crawl_samsungfire_faq():
    target_url = "https://www.samsungfire.com/vh/page/VH.HPCS0611.do"
    driver = create_stealth_driver()
    wait = WebDriverWait(driver, 10)
    faq_results = []

    try:
        driver.get(target_url)
        time.sleep(3)  # 초기 페이지 로딩 대기

        # 1. 질문분류(카테고리) 목록 추출 (button.ui-chip-btn)
        category_elements = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "button.ui-chip-btn")
            )
        )

        categories = []
        for elem in category_elements:
            cat_text = elem.text.strip()
            if cat_text and cat_text != "전체":
                categories.append(cat_text)

        print(f"[알림] 수집 대상 카테고리 목록 ({len(categories)}개): {categories}")

        # 2. 카테고리별 순회 수집
        for category_name in categories:
            print(f"\n>>> [{category_name}] 카테고리 수집 진행 중...")

            cat_buttons = wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "button.ui-chip-btn")
                )
            )

            target_btn = None
            for btn in cat_buttons:
                if category_name in btn.text.strip():
                    target_btn = btn
                    break

            if target_btn:
                driver.execute_script("arguments[0].click();", target_btn)
                time.sleep(2)  # 카테고리 클릭 후 데이터 로딩 대기
            else:
                print(f"  ! [{category_name}] 버튼을 찾을 수 없어 건너뜁니다.")
                continue

            current_page = 1

            # 3. 페이지네이션 순회
            while True:
                # 현재/전체 페이지 정보 파악 (div.page-numb -> "1 / 7")
                total_pages = 1
                try:
                    page_numb_elem = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.page-numb"))
                    )
                    page_info_text = page_numb_elem.text.strip()  # 예: "1 / 7"
                    
                    if "/" in page_info_text:
                        parts = page_info_text.split("/")
                        current_page = int(parts[0].strip())
                        total_pages = int(parts[1].strip())
                except Exception:
                    pass

                print(f"  - [{category_name}] {current_page} / {total_pages} 페이지 수집 중...")

                # FAQ 목록 대기 (dl.accordion-box)
                try:
                    wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "dl.accordion-box")
                        )
                    )
                    accordion_list = driver.find_elements(
                        By.CSS_SELECTOR, "dl.accordion-box"
                    )
                except TimeoutException:
                    print(f"  - [{category_name}] 수집할 FAQ 데이터가 없습니다.")
                    break

                # 페이지 내 FAQ 항목별 질문/답변 추출
                for accordion in accordion_list:
                    try:
                        head = accordion.find_element(
                            By.CSS_SELECTOR, "dt.accordion-head"
                        )
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", head
                        )

                        if "is-open" not in accordion.get_attribute("class"):
                            driver.execute_script("arguments[0].click();", head)
                            time.sleep(0.3)

                        question_elem = accordion.find_element(
                            By.CSS_SELECTOR, "div.tit-prd span.txt"
                        )
                        question = question_elem.text.strip()

                        answer_elem = accordion.find_element(
                            By.CSS_SELECTOR, "dd.accordion-body"
                        )
                        answer = answer_elem.get_attribute("innerText").strip()

                        faq_results.append(
                            {
                                "질문분류": category_name,
                                "질문": question,
                                "답변": answer,
                            }
                        )
                    except Exception as err:
                        print(f"    ! 항목 추출 오류 스킵: {err}")
                        continue

                # 마지막 페이지 도달 시 해당 카테고리 종료
                if current_page >= total_pages:
                    print(f"  - [{category_name}] 마지막 페이지 수집 완료 (총 {total_pages}페이지)")
                    break

                # 4. 다음 페이지 버튼 탐색 및 클릭
                try:
                    # page-numb 우측 control-wrap 내의 첫 번째 버튼/링크(다음 페이지 버튼)
                    next_btn_xpath = (
                        "//div[contains(@class, 'page-numb')]"
                        "/following-sibling::div[contains(@class, 'control-wrap')]"
                        "//button | //div[contains(@class, 'page-numb')]"
                        "/following-sibling::div[contains(@class, 'control-wrap')]//a"
                    )
                    next_button = driver.find_element(By.XPATH, next_btn_xpath)

                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", next_button
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(2)  # 다음 페이지 로딩 대기

                except NoSuchElementException:
                    print(f"  - [{category_name}] 다음 페이지 버튼을 찾지 못해 종료합니다.")
                    break

        # 5. CSV 파일 저장 (utf-8-sig 적용)
        if faq_results:
            df = pd.DataFrame(faq_results)
            df = df[["질문분류", "질문", "답변"]]

            file_name = "samsungfire_faq_data.csv"
            df.to_csv(file_name, index=False, encoding="utf-8-sig")
            print(
                f"\n[수집 완료] 총 {len(df)}건의 FAQ 데이터가 '{file_name}'으로 성공적으로 저장되었습니다."
            )
        else:
            print("\n[알림] 수집된 데이터가 없습니다.")

    finally:
        driver.quit()


if __name__ == "__main__":
    crawl_samsungfire_faq()