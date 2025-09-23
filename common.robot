*** Settings ***
Documentation     Общий ресурс после миграции: вся сложная логика живёт в excel_params.py
Library           SeleniumLibrary
Library           RequestsLibrary
Library           OperatingSystem
Library           Collections
Library           String
Library           libs/excel_params.py
Library           BuiltIn
Library           json
Library           libs/oracle_keywords.py

*** Variables ***
# ─────────── URLs ───────────
${BASE_URL}       https://192.168.84.200
${GRID_URL}       http://192.168.84.229:4444
# ─────────── Учётные данные ───────────
${USERNAME}       akuz
${PASSWORD}       aaa
# ─────────── Excel ───────────
${EXCEL_PATH}     report_fields.xlsx
${EXCEL_SHEET}    Sheet
# ─────────── Разное ───────────
${SEL_TIMEOUT}    30 s
${DB_USER}     report_user
${DB_PWD}      S3cret
${DB_HOST}     192.168.1.10
${SERVICE}     ORCLPDB1 


${DB_USER}        system
${DB_PWD}         psystemp
${DB_HOST}        192.168.84.200
${SERVICE}        central
${IC_DIR}         C:/svn/Ride/libs/instantclient23.8.0.25.04/instantclient_23_8

*** Keywords ***
Run Report
    [Arguments] ${report_id}
    Run Report From Excel ${report_id}

Open And Login Once
    Browser start

Browser stop
    [Documentation]    Закрывает все окна браузера
    Close All Browsers
