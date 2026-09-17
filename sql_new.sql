WITH olt_list AS (

    SELECT 'ADELIABZOL1' AS MGT_NE_NAME

),

network_elements AS (

    SELECT
        ne.NE_ODS_ID,
        ne.MGT_NE_NAME,
        ne.NE_UNIQUE_NAME,
        ne.NE_TYPE_DESC,
        ne.STRUCTURE_PS_ODS_ID

    FROM erl.cdw_cods_netinv.network_element ne

    INNER JOIN olt_list o
        ON ne.MGT_NE_NAME = o.MGT_NE_NAME

),

trails AS (
    SELECT DISTINCT
        ne.NE_ODS_ID,
        ne.MGT_NE_NAME,
        t.TRAIL_ODS_ID
    FROM network_elements ne
    INNER JOIN TRAIL t
        ON ne.NE_ODS_ID = t.NE_ODS_ID
)
SELECT *
FROM trails
ORDER BY TRAIL_ODS_ID;