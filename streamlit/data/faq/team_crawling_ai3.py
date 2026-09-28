import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def setup_stealth_driver():
    """
    고도화된 봇 탐지 우회 옵션이 적용된 Chrome Driver를 생성합니다.
    """
    options = webdriver.ChromeOptions()
    
    # 기본 브라우저 설정
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # 1. 봇 탐지 우회 핵심 옵션
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 2. 실제 사용자 User-Agent 설정
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # 3. navigator.webdriver 속성 재정의 (스텔스 우회)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })

    return driver

def scrape_kb_faq():
    target_url = (
        "https://direct.kbinsure.co.kr/home/#/WS/IS/COMN_4012M/"
        "?pid=1090041&code=0251&joinMall=Y&utm_source=Google"
        "&utm_medium=google%20CPC(%EC%9D%BC%EB%B0%98_%EB%B8%8C%EB%9E%9C%EB%93%9CKW)"
        "&utm_term=KB%EC%86%90%ED%95%B4%EB%B3%B4%ED%97%98%EC%9E%90%EB%8F%99%EC%B0%A8"
        "&utm_campaign=0706_1231_google_sa&utm_content=10900410251"
    )
    
    collected_data = []
    driver = setup_stealth_driver()
    wait = WebDriverWait(driver, 15)

    try:
        print("페이지 접속 중...")
        driver.get(target_url)
        time.sleep(3)  # 초기 리소스 로딩 대기

        # -------------------------------------------------------------
        # 1. 최초 1회 FAQ 버튼 클릭 (1번 이미지 기반)[cite: 5]
        # -------------------------------------------------------------
        print("1. FAQ 버튼 클릭 처리 중...")
        faq_btn_xpath = "//a[contains(@ng-click, 'openCarFAQPop') or contains(@class, 'btn_bnnr')]"
        faq_btn = wait.until(EC.presence_of_element_located((By.XPATH, faq_btn_xpath)))
        driver.execute_script("arguments[0].click();", faq_btn)
        time.sleep(2)

        # -------------------------------------------------------------
        # 2. '목록 더보기' 버튼을 반복 클릭하여 전체 243개 데이터 로딩 (6번 이미지 기반)[cite: 10]
        # -------------------------------------------------------------
        print("2. 전체 FAQ 목록 확장 ('목록 더보기' 클릭 중)...")
        more_btn_xpath = "//a[contains(@ng-click, 'addView')]"
        
        while True:
            try:
                # 목록 더보기 버튼 확인
                more_buttons = driver.find_elements(By.XPATH, more_btn_xpath)
                if not more_buttons or not more_buttons[0].is_displayed():
                    break
                
                # 클릭 수행
                driver.execute_script("arguments[0].click();", more_buttons[0])
                time.sleep(0.4)  # 연속 클릭 간격
                
                # 현재 노출된 질문 개수 로깅
                current_count = len(driver.find_elements(By.XPATH, "//a[starts-with(@id, 'list_')]"))
                print(f"   - 현재 노출된 질문 개수: {current_count}개")

                # 목표인 243개 이상 로딩 시 완료
                if current_count >= 243:
                    print("   -> 전체 243개 항목 로딩을 완료했습니다.")
                    break
            except Exception:
                break

        time.sleep(1)

        # -------------------------------------------------------------
        # 3. 질문 목록 수집 및 펼치기 후 답변 수집 (2, 3, 4, 5번 이미지 기반)[cite: 6, 7, 8, 9]
        # -------------------------------------------------------------
        print("3. 데이터 수집 및 정제 시작 (항목, 질문, 답변)...")
        question_links = driver.find_elements(By.XPATH, "//a[starts-with(@id, 'list_')]")
        total_items = len(question_links)
        print(f" -> 총 수집 대상: {total_items}개 항목")

        for index in range(total_items):
            # Stale Element 방지를 위한 동적 요소 대조
            q_link = driver.find_element(By.ID, f"list_{index}")

            # A. 항목(Category) 추출 및 정제 (2번 이미지)[cite: 6]
            try:
                parent_tr = q_link.find_element(By.XPATH, "./ancestor::tr")
                category_td = parent_tr.find_element(By.XPATH, "./td[contains(@class, 'ng-binding') or position()=1]")
                category_text = " ".join(category_td.text.split())  # 줄바꿈 및 공백 정돈
            except Exception:
                category_text = "기타"

            # [항목 전용 규칙] 특수 공백 제거 및 '>' 기호 기준 앞부분만 남기기
            category_text = category_text.replace("\xa0", " ")
            if ">" in category_text:
                category_text = category_text.split(">")[0].strip()

            # B. 질문(Question) 추출 (3번 이미지)[cite: 7]
            try:
                title_span = q_link.find_element(By.XPATH, ".//span[contains(@ng-bind-html, 'FAQ_TITLE_NM')]")
                raw_q = title_span.text.strip()
            except Exception:
                raw_q = q_link.text.strip()

            # "Q." 접두사 처리 (기존 중복 Q. 제거 후 정형화)
            if raw_q.startswith("Q.") or raw_q.startswith("Q ."):
                clean_q = raw_q.split(".", 1)[-1].strip()
            elif raw_q.startswith("Q"):
                clean_q = raw_q[1:].strip()
            else:
                clean_q = raw_q
            
            # C. 답변 펼치기 버튼 클릭 (4번 이미지)[cite: 8]
            driver.execute_script("arguments[0].click();", q_link)
            time.sleep(0.15)  # 애니메이션 대기

            # D. 답변(Answer) 추출 (5번 이미지)[cite: 9]
            answer_tr_id = f"ask{index}"
            try:
                answer_span = driver.find_element(By.XPATH, f"//tr[@id='{answer_tr_id}']//span[contains(@ng-bind-html, 'FAQ_TEXT')]")
                raw_a = answer_span.text.strip()
            except Exception:
                try:
                    answer_td = driver.find_element(By.XPATH, f"//tr[@id='{answer_tr_id}']//td[contains(@class, 'customer_answer')]")
                    raw_a = answer_td.text.strip()
                except Exception:
                    raw_a = ""

            # "A." 접두사 처리 (기존 중복 A. 제거 후 정형화)
            if raw_a.startswith("A.") or raw_a.startswith("A ."):
                clean_a = raw_a.split(".", 1)[-1].strip()
            elif raw_a.startswith("A"):
                clean_a = raw_a[1:].strip()
            else:
                clean_a = raw_a

            # E. 질문과 답변 내 쉼표(,)를 공백(" ")으로 치환
            clean_q = clean_q.replace(",", " ")
            clean_a = clean_a.replace(",", " ")

            # 접두사 부과
            final_question = f"Q. {clean_q}"
            final_answer = f"A. {clean_a}"

            # 수집 목록 저장
            collected_data.append({
                "항목": category_text,
                "질문": final_question,
                "답변": final_answer
            })

            if (index + 1) % 50 == 0 or (index + 1) == total_items:
                print(f"   - 수집 진행률: {index + 1}/{total_items} 완료")

        # -------------------------------------------------------------
        # 4. CSV 파일로 저장 (인코딩: utf-8-sig)
        # -------------------------------------------------------------
        df = pd.DataFrame(collected_data)
        df = df[["항목", "질문", "답변"]]  # 3개 컬럼 순서 고정

        output_filename = "kb_insurance_faq_243.csv"
        df.to_csv(output_filename, index=False, encoding="utf-8-sig")
        print(f"\n[성공] 총 {len(collected_data)}건의 데이터를 '{output_filename}' 파일로 저장하였습니다.")

    except Exception as e:
        print(f"\n[오류 발생]: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_kb_faq()
