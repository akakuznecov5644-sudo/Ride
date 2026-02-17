*** Settings ***
Suite Setup       Open And Login Once
Suite Teardown    Browser stop
Resource          common.robot
Library           libs/Jackpots.py
Library           libs/excel_params.py

*** Test Cases ***
Create Jackpot Mystery
    [Documentation]    Создание Jackpot типа Mystery.
    ${suffix}=    Evaluate    __import__('time').time_ns() % 100000
    ${jp_name}=    Set Variable    JP_AUTOTEST_MYSTERY_${suffix}
    Open Jackpot Create Form
    Fill Jackpot Common Fields    ${jp_name}    Mystery
    Click By Text    Save
    Expect Error    Jackpot ${jp_name} created successfully

Create Jackpot Normal
    [Documentation]    Создание Jackpot типа Normal.
    ${suffix}=    Evaluate    __import__('time').time_ns() % 100000
    ${jp_name}=    Set Variable    JP_AUTOTEST_NORMAL_${suffix}
    Open Jackpot Create Form
    Fill Jackpot Common Fields    ${jp_name}    Normal
    Click By Text    Save
    Expect Error    Jackpot ${jp_name} created successfully

Create Jackpot Lucky Chance Fixed Prize
    [Documentation]    Создание Jackpot типа Lucky Chance с Subtype = Fixed Prize.
    ${suffix}=    Evaluate    __import__('time').time_ns() % 100000
    ${jp_name}=    Set Variable    JP_AUTOTEST_LC_FIXED_${suffix}
    Open Jackpot Create Form
    Fill Jackpot Common Fields    ${jp_name}    Lucky Chance
    Select By Attr    id="lc_progressive_contribution"    Fixed Prize
    Click By Text    Save
    Expect Error    Jackpot ${jp_name} created successfully

Create Jackpot Lucky Chance Progressive
    [Documentation]    Создание Jackpot типа Lucky Chance с Subtype = Progressive.
    ${suffix}=    Evaluate    __import__('time').time_ns() % 100000
    ${jp_name}=    Set Variable    JP_AUTOTEST_LC_PROG_${suffix}
    Open Jackpot Create Form
    Fill Jackpot Common Fields    ${jp_name}    Lucky Chance
    Select By Attr    id="lc_progressive_contribution"    Progressive
    Click By Text    Save
    Expect Error    Jackpot ${jp_name} created successfully

*** Keywords ***
Open Jackpot Create Form
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Click By Attr    data-menu-id="jackpots"
    Click By Attr    data-menu-id="jackpotManager"
    Wait Until Page Has    xpath://span[contains(., 'Prizes')]
    Click By Attr    title="Create Jackpot"
    Wait Until Page Has    xpath://div[contains(@class,'ant-modal-content')]//div[contains(@class,'ant-tabs-tab-btn') and normalize-space(.)='General']
    Wait Until Page Has    xpath://div[contains(@class,'ant-modal-content')]//input[@id='code_desc' and not(@disabled)]

Fill Jackpot Common Fields
    [Arguments]    ${jp_name}    ${jp_type}
    Fill By Attr      id="code_desc"                 ${jp_name}
    Select By Attr    id="progressive_type"          ${jp_type}
    Select By Attr    id="currency_code"             EUR
    Select By Attr    id="sas_group_id"              1
    Select By Attr    id="sas_level_id"              1
    Fill By Attr      id="jackpot_reset_amount"      50
    Fill By Attr      id="min_hit_amount"            10
    Fill By Attr      id="max_jackpot_amount"        100000
    Fill By Attr      id="default_pct"               1
    Fill By Attr      id="min_bet_amount"            1
    Fill By Attr      id="max_bet_amount"            100
    Fill By Attr      id="bc_point"                  500

