*** Settings ***
Suite Setup       Open And Login Once
Suite Teardown    Browser stop
Resource          common.robot

*** Test Cases ***
succes login
    [Documentation]    Проверяем, что логин прошёл и мы попали на дашборд
    Open Oracle Connection
    Close Oracle Connection
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Click By Attr    data-menu-id="cage"
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    Gaming
    Fill Date By Attr    placeholder="Start date"    22.07.2024
    Fill Date By Attr    placeholder="End date"    22.07.2025
    Click By Text    Show
    Sleep    20 s

report 204
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/204
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Fill Date By Attr    placeholder="Start date"    31.07.2024 0:00
    Fill Date By Attr    placeholder="End date"    06.08.2025 23:59
    Click By Text    Show
    Open Date Filter    Date
    Fill Date By Attr    placeholder="Select date"    31.07.2024 0:00:02
    Click By Attr    class="anticon-check-circle"
    Sleep    20 s

report 307
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/307
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    Gaming2
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    Wait Until Page Has    xpath://div[contains(., 'EUR')]
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text    OK
    Click By Attr    title="Clear all filters"
    open_multiselect_filter    Transaction Type
    Sleep    1 s
    Click By Text On Filter    Handmade transaction
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Open Text Filter    Internal Number
    Fill Text On Filter    "010002361209"
    Click By Attr    title="Clear all filters"
    open_multiselect_filter    Card Type
    Sleep    1 s
    Click By Text On Filter    Muhaha
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Open Text Filter    Player
    Fill Text On Filter    "Aaaaaa Zzzzzzz"
    Click By Attr    title="Clear all filters"
    Scroll X By Text    Amount    to=center
    Open DateTime Filter    Birth Date
    Fill Date By Attr    placeholder="Select date"    01.01.2000
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Open Numeric Filter    Amount
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    20 s

report 307 scroll
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/307
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    Gaming2
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    Wait Until Page Has    xpath://div[contains(., 'EUR')]
    Scroll X By Text    Amount    to=center
    Sleep    20 s

report 307 опытный
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/307
    # Параметры отчёта
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    All locations
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    # -------- Левый блок колонок --------
    Wait Until Page Has    xpath://div[contains(., 'EUR')]
    # Currency (multiselect)
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Transaction Type (multiselect)
    Open Multiselect Filter    Transaction Type
    Click By Text On Filter    Handmade transaction
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Internal Number (text)
    Open Text Filter    Internal Number
    Fill Text On Filter    "010002361209"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Printed Number (text)
    Open Text Filter    Printed Number
    Fill Text On Filter    "00000000016"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Card Type (multiselect)
    Open Multiselect Filter    Card Type
    Click By Text On Filter    EURO
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Player (text)
    Open Text Filter    Player
    Fill Text On Filter    "Aaaaaa Zzzzzzz"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # -------- Прокрутка к середине --------
    Scroll X By Text    Amount    to=center
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Birth Date
    Fill Date By Attr    placeholder="Select date"    01.01.2000
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Amount (numeric)
    Open Numeric Filter    Amount
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Balance Before (numeric)
    Open Numeric Filter    Balance Before
    Fill Text On Filter    "300.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Balance After (numeric)
    Open Numeric Filter    Balance After
    Fill Text On Filter    "423.45"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Cashier (text)
    Open Text Filter    Employee
    Fill Text On Filter    "Liz"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Login (text)
    Open Text Filter    Login
    Fill Text On Filter    "MATVEY"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Comments (text)
    Open Text Filter    Reason
    Fill Text On Filter    "123"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # -------- Прокрутка вправо --------
    Scroll X By Text    ID Type    to=center
    Sleep    1 s
    # Entry Date (datetime)
    Open DateTime Filter    class="ENTRY_DATE"
    Fill Date By Attr    placeholder="Select date"    20.05.2025 17:17:55
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Location (multiselect)
    Open Multiselect Filter    Location
    Click By Attr    data-menu-id="Gaming2"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # ID Type (multiselect)
    Scroll X By Text    ID Type    to=center
    Open Text Filter    ID Type
    Fill Text On Filter    Passport
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # ID Number (text)
    Scroll X By Text    ID Number    to=center
    Open Text Filter    ID Number
    Fill Text On Filter    "666"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Финальный скрин/сброс
    Step Screenshot    Report 307 - all filters passed
    Sleep    20 s

report 312
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/312
    # Параметры отчёта
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    All locations
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    # Printed Number (text)
    Open Text Filter    Printed Number
    Fill Text On Filter    "00000001717"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Card Type (multiselect)
    Open Multiselect Filter    Card Type
    Click By Text On Filter    EURO
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Player (text)
    Open Text Filter    Player
    Fill Text On Filter    "Gnito Inco"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Entry Date (datetime)
    Open DateTime Filter    Date Of Adjustment
    Fill Date By Attr    placeholder="Select date"    21.11.2024 20:41:39
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    # Cashier (text)
    Open Text Filter    Employee
    Fill Text On Filter    "Liz"
    Click By Attr    title="Clear all filters"
    # Amount (numeric)
    Open Numeric Filter    Amount
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Comments (text)
    Open Text Filter    Reason
    Fill Text On Filter    "Player's registration"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Comments (text)
    Open Text Filter    Comment
    Fill Text On Filter    "123"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Currency (multiselect)
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Location (multiselect)
    Open Multiselect Filter    Location
    Click By Attr    data-menu-id="Gaming2"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Birth Date
    Fill Date By Attr    placeholder="Select date"    01.01.2001
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # ID Type (multiselect)
    Scroll X By Text    ID Type    to=center
    Open Text Filter    ID Type
    Fill Text On Filter    Passport
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # ID Number (text)
    Scroll X By Text    ID Number    to=center
    Open Text Filter    ID Number
    Fill Text On Filter    "666"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Internal Number (text)
    Open Text Filter    Internal Number
    Fill Text On Filter    "010002361209"
    Click By Attr    title="Clear all filters"
    # Финальный скрин/сброс
    Step Screenshot    Report 307 - all filters passed
    Sleep    20 s

Report 302
    Login
    Open Url    https://192.168.84.200/report/page/332
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    # Параметры отчёта
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Fill Date By Attr    placeholder="Start date"    18.08.2024 23:59
    Fill Date By Attr    placeholder="End date"    06.08.2025 23:59
    Click By Text    Show
    #date
    Open DateTime Filter    Date
    Fill Date By Attr    placeholder="Select date"    15.08.2025 16:29:41
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Action (multiselect)
    Open Multiselect Filter    Action
    Click By Attr    data-menu-id="GRANT"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Administrator (multiselect)
    Open Multiselect Filter    Administrator
    Click By Attr    data-menu-id="ACPSA"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # User (text)
    Open Text Filter    User
    Fill Text On Filter    "ABAZ"
    Click By Attr    title="Clear all filters"
    Sleep    1 s

Report 332
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/332
    # Параметры отчёта
    Wait Until Page Has    xpath://li[contains(., 'Total rows')]
    # Name (text)
    Open Text Filter    Name
    Fill Text On Filter    "00000001717"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Transaction Type (multiselect)
    Open Multiselect Filter    Status
    Click By Text On Filter    Active
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Transaction Type (multiselect)
    Open Multiselect Filter    Type
    Click By Text On Filter    Coupon
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Open Text Filter    Expected Participants
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Open Text Filter    Budget Left
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Open Text Filter    Budget Spent
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Scroll X By Text    Currency    to=center
    Open Text Filter    Total Budget
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Currency (multiselect)
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Promotion Start
    Fill Date By Attr    placeholder="Select date"    01.01.2001
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Promotion End
    Fill Date By Attr    placeholder="Select date"    01.01.2001
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    Step Screenshot    Report 307 - all filters passed
    Sleep    20 s

Report 333
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/333
    # Параметры отчёта
    Wait Until Page Has    xpath://li[contains(., 'Total rows')]
    # Name (text)
    Open Text Filter    Name
    Fill Text On Filter    "00000001717"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Transaction Type (multiselect)
    Open Multiselect Filter    Status
    Click By Text On Filter    Finished
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Transaction Type (multiselect)
    Open Multiselect Filter    Type
    Click By Text On Filter    Coupon
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Open Text Filter    Budget Left
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Open Text Filter    Budget Spent
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Name (text)
    Scroll X By Text    Currency    to=center
    Open Text Filter    Total Budget
    Fill Text On Filter    0
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Currency (multiselect)
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Promotion Start
    Fill Date By Attr    placeholder="Select date"    01.01.2001
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Birth Date (date)
    Open DateTime Filter    Promotion End
    Fill Date By Attr    placeholder="Select date"    01.01.2001
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    Step Screenshot    Report 307 - all filters passed
    Sleep    20 s

Report 369
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/369
    # Параметры отчёта
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    All locations
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    # Promotion Name (multiselect)
    Open Multiselect Filter    Promotion Name
    Click By Attr    data-menu-id="BD_TEST"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Player (text)
    Open Text Filter    Player
    Fill Text On Filter    Lee Mark
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Location (multiselect)
    Open Multiselect Filter    Location
    Click By Attr    data-menu-id="Gaming"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Currency (multiselect)
    Open Multiselect Filter    Currency
    Click By Attr    data-menu-id="EUR"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Card Number (text)
    Open Text Filter    Card Number
    Fill Text On Filter    "00000000002"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Internal Number (text)
    Open Text Filter    Card Number
    Fill Text On Filter    "12345"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    Scroll X By Text    Amount    to=center
    Sleep    1 s
    # Amount (numeric)
    Open Numeric Filter    Amount
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Ticket Status (multiselect)
    Open Multiselect Filter    Ticket Status
    Click By Attr    data-menu-id="Redeemed"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Validation Number (text)
    Open Text Filter    Card Number
    Fill Text On Filter    "0043"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Print Mach Id (multiselect)
    Open Multiselect Filter    Print Mach Id
    Click By Attr    data-menu-id="OGMS"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Print Date (datetime)
    Open DateTime Filter    class="PRINT_DATE"
    Fill Date By Attr    placeholder="Select date"    13.05.2025 18:37:38
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Expiration Date (datetime)
    Open DateTime Filter    class="EXPIRATION_DATE"
    Fill Date By Attr    placeholder="Select date"    20.06.2025 18:39:00
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Redeem Date (datetime)
    Open DateTime Filter    Redeem Date
    Fill Date By Attr    placeholder="Select date"    24.03.2025 14:15:16
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Redeem Mach Id (multiselect)
    Open Multiselect Filter    Redeem Mach Id
    Click By Attr    data-menu-id="911"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Redeem Position (multiselect)
    Open Multiselect Filter    Redeem Position
    Click By Attr    data-menu-id="911911"
    Click By Text On Filter    OK
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Session Start (datetime)
    Open DateTime Filter    Session Start
    Fill Date By Attr    placeholder="Select date"    24.03.2025 14:15:04
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Session End (datetime)
    Open DateTime Filter    Session End
    Fill Date By Attr    placeholder="Select date"    24.03.2025 14:15:51
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Bet (numeric)
    Open Numeric Filter    Bet
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Promo Bet (numeric)
    Open Numeric Filter    Promo Bet
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Promo Ticket In (numeric)
    Open Numeric Filter    Promo Ticket In
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Amount (numeric)
    Open Numeric Filter    class="TICKET_IN"
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Bills In (numeric)
    Open Numeric Filter    Bills In
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s

Report 369_2
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Open Url    https://192.168.84.200/report/page/369
    # Параметры отчёта
    Wait Until Page Has    xpath://span[contains(., 'Report parameters')]
    Click By Text    Report parameters
    Wait Until Page Has    xpath://span[contains(., 'Show')]
    Select By Attr    id="query_location_id"    All locations
    Fill Date By Attr    placeholder="Start date"    31.07.2024
    Fill Date By Attr    placeholder="End date"    06.08.2025
    Click By Text    Show
    # Promo Ticket In (numeric)
    Open Numeric Filter    Promo Ticket In
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Amount (numeric)
    Open Numeric Filter    class="TICKET_IN"
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s
    # Bills In (numeric)
    Open Numeric Filter    Bills In
    Fill Text On Filter    "10 000.00"
    Click By Attr On Filter    aria-label="check-circle"
    Click By Attr    title="Clear all filters"
    Sleep    1 s

Report 312 – авто-проверка фильтров
    Check Report Filters    312
    ...    report_parameters
    ...    location=All locations
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 369 – авто-проверка фильтров
    Check Report Filters    369
    ...    report_parameters
    ...    location=All locations
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 204 – авто-проверка фильтров
    Check Report Filters    204
    ...    report_parameters
    ...    start_date=31.07.2024 0:00
    ...    end_date=06.08.2025 0:00
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 202 – авто-проверка фильтров
    Check Report Filters    202
    ...    report_parameters
    ...    location=All locations
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 317 – авто-проверка фильтров
    Check Report Filters    317
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 235 – авто-проверка фильтров
    Check Report Filters    235
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 233 – авто-проверка фильтров
    Check Report Filters    233
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 307 – авто-проверка фильтров
    Check Report Filters    307
    ...    report_parameters
    ...    location=All locations
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 298 – авто-проверка фильтров
    Check Report Filters    298
    ...    report_parameters
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 332 – авто-проверка фильтров
    Check Report Filters    332
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 333 – авто-проверка фильтров
    Check Report Filters    333
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 66 – авто-проверка фильтров
    Check Report Filters    66
    ...    report_parameters
    ...    location=Gaming2
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 371 – авто-проверка фильтров
    Check Report Filters    371
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 243 – авто-проверка фильтров
    Check Report Filters    243
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 324 – авто-проверка фильтров
    Check Report Filters    324
    ...    flags_to_check=Active only,Include archived
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 265 – авто-проверка фильтров
    Check Report Filters    265
    ...    report_parameters
    ...    params_extra=text|attr='id="query_mach_id"'|200
    ...    start_date=31.07.2024 0:00
    ...    end_date=06.08.2025 0:00
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 125 – авто-проверка фильтров
    Check Report Filters    125
    ...    report_parameters
    ...    location=Gaming2
    ...    start_date=31.07.2024 0:00
    ...    end_date=06.08.2025 0:00
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 278 – авто-проверка фильтров
    Check Report Filters    278
    ...    report_parameters
    ...    params_extra1=select|attr='id="query_location_id"'|Gaming2
    ...    params_extra2=select|attr='id="query_currency_id"'|EUR
    ...    start_date=31.07.2024
    ...    end_date=06.08.2025
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 65 – авто-проверка фильтров
    Check Report Filters    65
    ...    report_parameters
    ...    params_extra1=select|attr='id="query_location_id"'|Gaming2
    ...    start_date=31.07.2025
    ...    end_date=06.08.2025
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True

Report 225 – авто-проверка фильтров
    Check Report Filters    225
    ...    max_columns=all
    ...    console_check_kw=Assert Console Has No Errors
    ...    network_check_kw=Assert No Failed Requests
    ...    checks_when=after_params,per_column,final
    ...    fail_on_check=True
