*** Settings ***
Suite Setup       Open And Login Once
Suite Teardown    Browser stop
Resource          common.robot

*** Test Cases ***
Smoke IOC
    Login
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}
    Click By Attr    data-menu-id="admin"
    Wait Until Page Has    xpath://span[contains(., 'User manager')]
    Click By Attr    data-menu-id="userManager"
    Wait Until Page Has    xpath://a[contains(., 'Edit')]
    Click Row Action By Login    Login    IOCTEST    Actions    Edit    table_index=1
    Wait Until Page Has    xpath://div[contains(., 'Main info')]
    Click By Attr    id="webRoles"    index=2
    Click Row Action By Login    Role name    IOCTEST    Granted    ""    table_index=2
    Wait For AntD Notification    Access is allowed
    Open Url    https://192.168.84.220/login
    Logpass    ioctest    iii
    Wait Until Page Has    xpath=//img[contains(@src, "/images/myacp.png")]    ${SEL_TIMEOUT}

remove IOC
    Click By Attr    data-menu-id="admin"
    Wait Until Page Has    xpath://span[contains(., 'IOC and GLM configuration')]
    Click By Attr    data-menu-id="iocglm"
    Sleep    2 s
    Delete GLMs Where IOC Not Zero
    Sleep    2 s
    Delete Non-Zero IOCs
    Sleep    2 s

Create IOC
    Add IOC    1
    Sleep    2 s

Create GLM
    Add GLM    1
    Sleep    2 s

Error check
    Add GLM With Existing Unique Code
    Expect Error    GLM with this unique code already exists
    Sleep    2 s
    Open Url    https://192.168.84.220/iocglm/dashboard
    Sleep    2 s
    Add GLM With Existing Certificate
    Expect Error    GLM with this certificate already exists
    Sleep    2 s
    Open Url    https://192.168.84.220/iocglm/dashboard
    Wait Until Page Has    xpath://a[contains(., 'Edit')]

Remove GLM
    Delete GLMs Where IOC Not Zero
    Sleep    2 s

Remove IOC
    Delete Non-Zero IOCs
    Sleep    2 s
