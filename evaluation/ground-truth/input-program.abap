*&---------------------------------------------------------------------*
*& Report ZR_SD_OPEN_ORDER_MARGIN_COCKPIT
*&---------------------------------------------------------------------*
*& Open Sales Order Fulfillment & Margin Cockpit
*&
*& Reads open sales orders for a sales organisation, determines the
*& processing / delivery / billing status, calculates the order margin
*& from the pricing conditions, evaluates the customer credit situation
*& and optionally creates a follow-up sales order for incomplete items.
*&
*& Original author : (legacy ECC object - training baseline)
*& Module          : SD
*&---------------------------------------------------------------------*
REPORT zr_sd_open_order_margin_cockpit LINE-SIZE 255 LINE-COUNT 65.

*&---------------------------------------------------------------------*
*& Tables / DDIC work areas
*&---------------------------------------------------------------------*
TABLES: vbak,
        vbap,
        vbuk,
        vbup,
        konv,
        knkk,
        mara,
        likp,
        vbrk.

*&---------------------------------------------------------------------*
*& Global types
*&---------------------------------------------------------------------*
TYPES: BEGIN OF ty_order,
         vbeln TYPE vbak-vbeln,
         auart TYPE vbak-auart,
         vkorg TYPE vbak-vkorg,
         vtweg TYPE vbak-vtweg,
         spart TYPE vbak-spart,
         kunnr TYPE vbak-kunnr,
         netwr TYPE vbak-netwr,
         waerk TYPE vbak-waerk,
         knumv TYPE vbak-knumv,
         erdat TYPE vbak-erdat,
         audat TYPE vbak-audat,
         vbtyp TYPE vbak-vbtyp,
       END OF ty_order.

TYPES: BEGIN OF ty_item,
         vbeln  TYPE vbap-vbeln,
         posnr  TYPE vbap-posnr,
         matnr  TYPE vbap-matnr,
         kwmeng TYPE vbap-kwmeng,
         netwr  TYPE vbap-netwr,
         netpr  TYPE vbap-netpr,
         werks  TYPE vbap-werks,
         pstyv  TYPE vbap-pstyv,
         abgru  TYPE vbap-abgru,
       END OF ty_item.

TYPES: BEGIN OF ty_hstat,
         vbeln TYPE vbuk-vbeln,
         gbstk TYPE vbuk-gbstk,
         lfstk TYPE vbuk-lfstk,
         fkstk TYPE vbuk-fkstk,
         uvall TYPE vbuk-uvall,
         uvprs TYPE vbuk-uvprs,
       END OF ty_hstat.

TYPES: BEGIN OF ty_istat,
         vbeln TYPE vbup-vbeln,
         posnr TYPE vbup-posnr,
         gbsta TYPE vbup-gbsta,
         lfsta TYPE vbup-lfsta,
         fksta TYPE vbup-fksta,
       END OF ty_istat.

TYPES: BEGIN OF ty_cond,
         knumv TYPE konv-knumv,
         kposn TYPE konv-kposn,
         stunr TYPE konv-stunr,
         zaehk TYPE konv-zaehk,
         kschl TYPE konv-kschl,
         kbetr TYPE konv-kbetr,
         kwert TYPE konv-kwert,
         waers TYPE konv-waers,
         kpein TYPE konv-kpein,
         kmein TYPE konv-kmein,
       END OF ty_cond.

TYPES: BEGIN OF ty_credit,
         kunnr TYPE knkk-kunnr,
         kkber TYPE knkk-kkber,
         klimk TYPE knkk-klimk,
         skfor TYPE knkk-skfor,
         ssobl TYPE knkk-ssobl,
         sauft TYPE knkk-sauft,
       END OF ty_credit.

TYPES: BEGIN OF ty_matkey,
         matnr TYPE mara-matnr,
         mtart TYPE mara-mtart,
         matkl TYPE mara-matkl,
         meins TYPE mara-meins,
       END OF ty_matkey.

TYPES: BEGIN OF ty_index,
         matnr TYPE vapma-matnr,
         vbeln TYPE vapma-vbeln,
         posnr TYPE vapma-posnr,
         kunnr TYPE vapma-kunnr,
         vkorg TYPE vapma-vkorg,
       END OF ty_index.

TYPES: BEGIN OF ty_out,
         vbeln       TYPE vbak-vbeln,
         posnr       TYPE vbap-posnr,
         kunnr       TYPE vbak-kunnr,
         matnr       TYPE vbap-matnr,
         matnr_legacy TYPE c LENGTH 18,
         maktx       TYPE makt-maktx,
         kwmeng      TYPE vbap-kwmeng,
         netwr       TYPE vbap-netwr,
         cost        TYPE vbap-netwr,
         margin      TYPE vbap-netwr,
         margin_pct  TYPE p LENGTH 7 DECIMALS 2,
         gbstk       TYPE vbuk-gbstk,
         lfstk       TYPE vbuk-lfstk,
         fkstk       TYPE vbuk-fkstk,
         gbsta       TYPE vbup-gbsta,
         credit_ok   TYPE c LENGTH 1,
         waerk       TYPE vbak-waerk,
       END OF ty_out.

*&---------------------------------------------------------------------*
*& Global data
*&---------------------------------------------------------------------*
DATA: gt_order  TYPE STANDARD TABLE OF ty_order,
      gt_item   TYPE STANDARD TABLE OF ty_item,
      gt_hstat  TYPE STANDARD TABLE OF ty_hstat,
      gt_istat  TYPE STANDARD TABLE OF ty_istat,
      gt_cond   TYPE STANDARD TABLE OF ty_cond,
      gt_credit TYPE STANDARD TABLE OF ty_credit,
      gt_matkey TYPE STANDARD TABLE OF ty_matkey,
      gt_index  TYPE STANDARD TABLE OF ty_index,
      gt_out    TYPE STANDARD TABLE OF ty_out.

DATA: gs_order  TYPE ty_order,
      gs_item   TYPE ty_item,
      gs_hstat  TYPE ty_hstat,
      gs_istat  TYPE ty_istat,
      gs_cond   TYPE ty_cond,
      gs_credit TYPE ty_credit,
      gs_matkey TYPE ty_matkey,
      gs_index  TYPE ty_index,
      gs_out    TYPE ty_out.

* legacy fixed length working fields
DATA: gv_matnr_old   TYPE c LENGTH 18,
      gv_matnr_18    TYPE c LENGTH 18,
      gv_vbtyp_char  TYPE c LENGTH 1,
      gv_maktx       TYPE makt-maktx,
      gv_total_marg  TYPE vbap-netwr,
      gv_total_netwr TYPE vbap-netwr,
      gv_kbetr       TYPE konv-kbetr,
      gv_netwr_db    TYPE vbak-netwr,
      gv_count       TYPE i.

*&---------------------------------------------------------------------*
*& Constants
*&---------------------------------------------------------------------*
CONSTANTS: gc_matnr_dummy TYPE c LENGTH 18 VALUE '000000000000DUMMY1',
           gc_vbtyp_order TYPE c LENGTH 1  VALUE 'C',
           gc_cond_price  TYPE konv-kschl  VALUE 'PR00',
           gc_cond_cost   TYPE konv-kschl  VALUE 'VPRS',
           gc_open        TYPE c LENGTH 1  VALUE 'A',
           gc_yes         TYPE c LENGTH 1  VALUE 'X'.

*&---------------------------------------------------------------------*
*& Selection screen
*&---------------------------------------------------------------------*
SELECTION-SCREEN BEGIN OF BLOCK b1 WITH FRAME TITLE text-001.
PARAMETERS:     p_vkorg TYPE vbak-vkorg OBLIGATORY.
SELECT-OPTIONS: s_vtweg FOR vbak-vtweg,
                s_spart FOR vbak-spart,
                s_auart FOR vbak-auart,
                s_kunnr FOR vbak-kunnr,
                s_matnr FOR vbap-matnr,
                s_erdat FOR vbak-erdat,
                s_vbeln FOR vbak-vbeln.
SELECTION-SCREEN END OF BLOCK b1.

SELECTION-SCREEN BEGIN OF BLOCK b2 WITH FRAME TITLE text-002.
PARAMETERS: p_open  AS CHECKBOX DEFAULT 'X',
            p_creat AS CHECKBOX,
            p_chg   AS CHECKBOX,
            p_kkber TYPE knkk-kkber.
SELECTION-SCREEN END OF BLOCK b2.

*&---------------------------------------------------------------------*
*& Initialization
*&---------------------------------------------------------------------*
INITIALIZATION.
  CLEAR: gv_count, gv_total_marg, gv_total_netwr.

*&---------------------------------------------------------------------*
*& At selection screen
*&---------------------------------------------------------------------*
AT SELECTION-SCREEN.
  IF p_vkorg IS INITIAL.
    MESSAGE 'Please enter a sales organisation' TYPE 'E'.
  ENDIF.

*&---------------------------------------------------------------------*
*& Start of selection
*&---------------------------------------------------------------------*
START-OF-SELECTION.

  PERFORM get_orders.
  PERFORM get_items.
  PERFORM get_header_status.
  PERFORM get_item_status.
  PERFORM get_conditions.
  PERFORM get_credit.
  PERFORM get_material_master.
  PERFORM get_index_data.
  PERFORM build_output.
  PERFORM read_netwr_native.

  IF p_creat = gc_yes.
    PERFORM create_followup_orders.
  ENDIF.

  IF p_chg = gc_yes.
    PERFORM change_open_orders.
  ENDIF.

*&---------------------------------------------------------------------*
*& End of selection
*&---------------------------------------------------------------------*
END-OF-SELECTION.

  PERFORM display_list.

*&---------------------------------------------------------------------*
*&      Form  get_orders
*&---------------------------------------------------------------------*
*&      Reads the sales order headers for the selection.
*&---------------------------------------------------------------------*
FORM get_orders.

  SELECT vbeln
         auart
         vkorg
         vtweg
         spart
         kunnr
         netwr
         waerk
         knumv
         erdat
         audat
         vbtyp
    FROM vbak
    INTO TABLE gt_order
    WHERE vkorg = p_vkorg
      AND vtweg IN s_vtweg
      AND spart IN s_spart
      AND auart IN s_auart
      AND kunnr IN s_kunnr
      AND erdat IN s_erdat
      AND vbeln IN s_vbeln.

  IF sy-subrc <> 0.
    MESSAGE 'No sales orders found for selection' TYPE 'I'.
    STOP.
  ENDIF.

* keep only real sales orders by document category
  LOOP AT gt_order INTO gs_order.
    gv_vbtyp_char = gs_order-vbtyp.
    IF gv_vbtyp_char <> gc_vbtyp_order.
      DELETE gt_order.
    ENDIF.
  ENDLOOP.

* sorted access is required later for the status merge
  SORT gt_order BY vbeln.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_items
*&---------------------------------------------------------------------*
*&      Reads the order items for all selected headers.
*&---------------------------------------------------------------------*
FORM get_items.

  SELECT *
    FROM vbap
    INTO CORRESPONDING FIELDS OF TABLE gt_item
    FOR ALL ENTRIES IN gt_order
    WHERE vbeln = gt_order-vbeln
      AND matnr IN s_matnr.

  IF p_open = gc_yes.
    DELETE gt_item WHERE abgru IS NOT INITIAL.
  ENDIF.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_header_status
*&---------------------------------------------------------------------*
*&      Reads the overall / delivery / billing status at header level.
*&---------------------------------------------------------------------*
FORM get_header_status.

  SELECT vbeln
         gbstk
         lfstk
         fkstk
         uvall
         uvprs
    FROM vbuk
    INTO TABLE gt_hstat
    FOR ALL ENTRIES IN gt_order
    WHERE vbeln = gt_order-vbeln.

  SORT gt_hstat BY vbeln.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_item_status
*&---------------------------------------------------------------------*
*&      Reads the processing status at item level.
*&---------------------------------------------------------------------*
FORM get_item_status.

  SELECT vbeln
         posnr
         gbsta
         lfsta
         fksta
    FROM vbup
    INTO TABLE gt_istat
    FOR ALL ENTRIES IN gt_item
    WHERE vbeln = gt_item-vbeln
      AND posnr = gt_item-posnr.

  SORT gt_istat BY vbeln posnr.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_conditions
*&---------------------------------------------------------------------*
*&      Reads the pricing condition records for the orders.
*&---------------------------------------------------------------------*
FORM get_conditions.

  SELECT knumv
         kposn
         stunr
         zaehk
         kschl
         kbetr
         kwert
         waers
         kpein
         kmein
    FROM konv
    INTO TABLE gt_cond
    FOR ALL ENTRIES IN gt_order
    WHERE knumv = gt_order-knumv.

  SORT gt_cond BY knumv kposn kschl.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_credit
*&---------------------------------------------------------------------*
*&      Reads the customer credit master data.
*&---------------------------------------------------------------------*
FORM get_credit.

  SELECT kunnr
         kkber
         klimk
         skfor
         ssobl
         sauft
    FROM knkk
    INTO TABLE gt_credit
    FOR ALL ENTRIES IN gt_order
    WHERE kunnr = gt_order-kunnr
      AND kkber = p_kkber.

  SORT gt_credit BY kunnr.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_material_master
*&---------------------------------------------------------------------*
*&      Reads selected material master attributes.
*&---------------------------------------------------------------------*
FORM get_material_master.

  IF gt_item IS INITIAL.
    RETURN.
  ENDIF.

  SELECT matnr
         mtart
         matkl
         meins
    FROM mara
    INTO TABLE gt_matkey
    FOR ALL ENTRIES IN gt_item
    WHERE matnr = gt_item-matnr.

  SORT gt_matkey BY matnr.

* legacy material number handling for the print layout
  LOOP AT gt_matkey INTO gs_matkey.
    gv_matnr_old = gs_matkey-matnr+0(18).
    IF gv_matnr_old = gc_matnr_dummy.
      DELETE gt_matkey.
    ENDIF.
  ENDLOOP.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_index_data
*&---------------------------------------------------------------------*
*&      Reads the order item index by material for cross reference.
*&---------------------------------------------------------------------*
FORM get_index_data.

  CHECK s_matnr[] IS NOT INITIAL.

  SELECT matnr
         vbeln
         posnr
         kunnr
         vkorg
    FROM vapma
    INTO TABLE gt_index
    WHERE matnr IN s_matnr
      AND vkorg = p_vkorg.

  SORT gt_index BY matnr vbeln posnr.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  build_output
*&---------------------------------------------------------------------*
*&      Combines all collected data into the output table and
*&      calculates the margin per item.
*&---------------------------------------------------------------------*
FORM build_output.

  DATA: lv_cost  TYPE vbap-netwr,
        lv_price TYPE vbap-netwr.

  LOOP AT gt_item INTO gs_item.

    CLEAR gs_out.
    gs_out-vbeln  = gs_item-vbeln.
    gs_out-posnr  = gs_item-posnr.
    gs_out-matnr  = gs_item-matnr.
    gs_out-kwmeng = gs_item-kwmeng.
    gs_out-netwr  = gs_item-netwr.

*   legacy 18 character material number for the report
    gs_out-matnr_legacy = gs_item-matnr+0(18).

*   header data
    READ TABLE gt_order INTO gs_order WITH KEY vbeln = gs_item-vbeln
                                       BINARY SEARCH.
    IF sy-subrc = 0.
      gs_out-kunnr = gs_order-kunnr.
      gs_out-waerk = gs_order-waerk.
    ENDIF.

*   material description - single read per item
    SELECT SINGLE maktx
      FROM makt
      INTO gv_maktx
      WHERE matnr = gs_item-matnr.
    gs_out-maktx = gv_maktx.

*   header status
    READ TABLE gt_hstat INTO gs_hstat WITH KEY vbeln = gs_item-vbeln
                                       BINARY SEARCH.
    IF sy-subrc = 0.
      gs_out-gbstk = gs_hstat-gbstk.
      gs_out-lfstk = gs_hstat-lfstk.
      gs_out-fkstk = gs_hstat-fkstk.
    ENDIF.

*   item status
    READ TABLE gt_istat INTO gs_istat WITH KEY vbeln = gs_item-vbeln
                                                posnr = gs_item-posnr
                                       BINARY SEARCH.
    IF sy-subrc = 0.
      gs_out-gbsta = gs_istat-gbsta.
    ENDIF.

*   condition based margin calculation
    PERFORM calc_margin USING    gs_order-knumv
                                 gs_item-posnr
                        CHANGING lv_price
                                 lv_cost.

    gs_out-netwr  = lv_price.
    gs_out-cost   = lv_cost.
    gs_out-margin = lv_price - lv_cost.
    IF lv_price <> 0.
      gs_out-margin_pct = ( gs_out-margin / lv_price ) * 100.
    ENDIF.

*   credit evaluation
    PERFORM check_credit USING    gs_out-kunnr
                         CHANGING gs_out-credit_ok.

    gv_total_marg  = gv_total_marg  + gs_out-margin.
    gv_total_netwr = gv_total_netwr + gs_out-netwr.
    gv_count       = gv_count + 1.

    APPEND gs_out TO gt_out.

  ENDLOOP.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  calc_margin
*&---------------------------------------------------------------------*
*&      Determines price and cost for an item from the conditions.
*&---------------------------------------------------------------------*
FORM calc_margin USING    iv_knumv TYPE konv-knumv
                          iv_posnr TYPE vbap-posnr
                 CHANGING cv_price TYPE vbap-netwr
                          cv_cost  TYPE vbap-netwr.

  DATA: lv_kposn TYPE konv-kposn.

  CLEAR: cv_price, cv_cost.
  lv_kposn = iv_posnr.

* price condition - single read on partial key
  SELECT SINGLE kwert
    FROM konv
    INTO cv_price
    WHERE knumv = iv_knumv
      AND kposn = lv_kposn
      AND kschl = gc_cond_price.

* cost condition - single read on partial key
  SELECT SINGLE kwert
    FROM konv
    INTO cv_cost
    WHERE knumv = iv_knumv
      AND kposn = lv_kposn
      AND kschl = gc_cond_cost.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  check_credit
*&---------------------------------------------------------------------*
*&      Evaluates whether the customer is within the credit limit.
*&---------------------------------------------------------------------*
FORM check_credit USING    iv_kunnr TYPE vbak-kunnr
                  CHANGING cv_ok    TYPE c.

  DATA: lv_exposure TYPE knkk-skfor.

  cv_ok = gc_yes.

  READ TABLE gt_credit INTO gs_credit WITH KEY kunnr = iv_kunnr
                                       BINARY SEARCH.
  IF sy-subrc = 0.
    lv_exposure = gs_credit-skfor + gs_credit-ssobl.
    IF lv_exposure > gs_credit-klimk AND gs_credit-klimk > 0.
      cv_ok = 'N'.
    ENDIF.
  ENDIF.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  read_netwr_native
*&---------------------------------------------------------------------*
*&      Cross checks the header net value directly on the database.
*&---------------------------------------------------------------------*
FORM read_netwr_native.

  DATA: lv_vbeln TYPE vbak-vbeln,
        lv_netwr TYPE vbak-netwr.

  LOOP AT gt_order INTO gs_order.

    lv_vbeln = gs_order-vbeln.
    CLEAR lv_netwr.

    EXEC SQL.
      SELECT NETWR INTO :lv_netwr
        FROM VBAK
        WHERE VBELN = :lv_vbeln
    ENDEXEC.

    IF lv_netwr <> gs_order-netwr.
      gv_netwr_db = lv_netwr.
    ENDIF.

  ENDLOOP.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  create_followup_orders
*&---------------------------------------------------------------------*
*&      Creates a follow-up sales order for rejected / incomplete items.
*&---------------------------------------------------------------------*
FORM create_followup_orders.

  DATA: ls_header  TYPE bapisdhd1,
        ls_headerx TYPE bapisdhd1x,
        lt_items   TYPE STANDARD TABLE OF bapisditm,
        ls_item    TYPE bapisditm,
        lt_itemsx  TYPE STANDARD TABLE OF bapisditmx,
        ls_itemx   TYPE bapisditmx,
        lt_partner TYPE STANDARD TABLE OF bapiparnr,
        ls_partner TYPE bapiparnr,
        lt_return  TYPE STANDARD TABLE OF bapiret2,
        ls_return  TYPE bapiret2,
        lv_vbeln   TYPE bapivbeln-vbeln,
        lv_posnr   TYPE posnr_va.

  LOOP AT gt_out INTO gs_out WHERE gbstk = gc_open.

    CLEAR: ls_header, ls_headerx.
    ls_header-doc_type   = 'TA'.
    ls_header-sales_org  = p_vkorg.
    ls_header-distr_chan = s_vtweg-low.
    ls_header-division   = s_spart-low.

    CLEAR ls_partner.
    REFRESH lt_partner.
    ls_partner-partn_role = 'AG'.
    ls_partner-partn_numb = gs_out-kunnr.
    APPEND ls_partner TO lt_partner.

    CLEAR ls_item.
    REFRESH lt_items.
    lv_posnr = lv_posnr + 10.
    ls_item-itm_number = lv_posnr.
    ls_item-material   = gs_out-matnr.
    ls_item-target_qty = gs_out-kwmeng.
    APPEND ls_item TO lt_items.

    CALL FUNCTION 'BAPI_SALESORDER_CREATEFROMDAT2'
      EXPORTING
        order_header_in     = ls_header
      IMPORTING
        salesdocument       = lv_vbeln
      TABLES
        return              = lt_return
        order_items_in      = lt_items
        order_partners      = lt_partner.

    READ TABLE lt_return INTO ls_return WITH KEY type = 'E'.
    IF sy-subrc = 0.
      CALL FUNCTION 'BAPI_TRANSACTION_ROLLBACK'.
    ELSE.
      CALL FUNCTION 'BAPI_TRANSACTION_COMMIT'
        EXPORTING
          wait = gc_yes.
      WRITE: / 'Follow-up order created:', lv_vbeln.
    ENDIF.

  ENDLOOP.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  change_open_orders
*&---------------------------------------------------------------------*
*&      Updates the delivery block on open orders.
*&---------------------------------------------------------------------*
FORM change_open_orders.

  DATA: ls_headerx TYPE bapisdh1x,
        lt_items   TYPE STANDARD TABLE OF bapisditm,
        ls_item    TYPE bapisditm,
        lt_itemsx  TYPE STANDARD TABLE OF bapisditmx,
        ls_itemx   TYPE bapisditmx,
        lt_return  TYPE STANDARD TABLE OF bapiret2,
        ls_return  TYPE bapiret2,
        lv_vbeln   TYPE bapivbeln-vbeln.

  LOOP AT gt_out INTO gs_out WHERE credit_ok = 'N'.

    lv_vbeln = gs_out-vbeln.

    CLEAR ls_headerx.
    ls_headerx-updateflag = 'U'.

    CLEAR: ls_item, ls_itemx.
    REFRESH: lt_items, lt_itemsx.
    ls_item-itm_number  = gs_out-posnr.
    ls_item-reason_rej  = '50'.
    APPEND ls_item TO lt_items.
    ls_itemx-itm_number = gs_out-posnr.
    ls_itemx-updateflag = 'U'.
    ls_itemx-reason_rej = gc_yes.
    APPEND ls_itemx TO lt_itemsx.

    CALL FUNCTION 'BAPI_SALESORDER_CHANGE'
      EXPORTING
        salesdocument    = lv_vbeln
        order_header_inx = ls_headerx
      TABLES
        return           = lt_return
        order_item_in    = lt_items
        order_item_inx   = lt_itemsx.

    READ TABLE lt_return INTO ls_return WITH KEY type = 'E'.
    IF sy-subrc <> 0.
      CALL FUNCTION 'BAPI_TRANSACTION_COMMIT'
        EXPORTING
          wait = gc_yes.
    ELSE.
      CALL FUNCTION 'BAPI_TRANSACTION_ROLLBACK'.
    ENDIF.

  ENDLOOP.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  read_material_detail
*&---------------------------------------------------------------------*
*&      Reads full material detail for an enrichment popup.
*&---------------------------------------------------------------------*
FORM read_material_detail USING iv_matnr TYPE matnr.

  DATA: ls_clientdata TYPE bapimatdoa,
        ls_return     TYPE bapiret2,
        lv_material   TYPE bapimatall-material.

  lv_material = iv_matnr.

  CALL FUNCTION 'BAPI_MATERIAL_GET_DETAIL'
    EXPORTING
      material       = lv_material
    IMPORTING
      material_general_data = ls_clientdata
      return                = ls_return.

  IF ls_return-type = 'E'.
    WRITE: / 'Material read failed:', iv_matnr.
  ENDIF.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  post_delivery_update
*&---------------------------------------------------------------------*
*&      Triggers a delivery update for confirmed items.
*&---------------------------------------------------------------------*
FORM post_delivery_update USING iv_vbeln TYPE likp-vbeln.

  DATA: lt_vbpok TYPE STANDARD TABLE OF vbpok,
        ls_vbpok TYPE vbpok,
        ls_vbkok TYPE vbkok.

  CLEAR ls_vbkok.
  ls_vbkok-vbeln_vl = iv_vbeln.
  ls_vbkok-vbtyp_vl = 'J'.

  CALL FUNCTION 'WS_DELIVERY_UPDATE'
    EXPORTING
      vbkok_wa  = ls_vbkok
      synchron  = gc_yes
      commit    = gc_yes
    TABLES
      vbpok_tab = lt_vbpok.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  get_credit_exposure
*&---------------------------------------------------------------------*
*&      Reads the classic credit exposure for a customer / credit area.
*&---------------------------------------------------------------------*
FORM get_credit_exposure USING    iv_kunnr TYPE kunnr
                                  iv_kkber TYPE kkber
                         CHANGING cv_open  TYPE knkk-skfor.

  DATA: lt_ccdetail TYPE STANDARD TABLE OF bapi_credit_exposure,
        ls_ccdetail TYPE bapi_credit_exposure,
        ls_return   TYPE bapireturn.

  CALL FUNCTION 'BAPI_CUSTOMER_GETCREDITACCOUNT'
    EXPORTING
      customer       = iv_kunnr
      creditcontrolarea = iv_kkber
    IMPORTING
      return         = ls_return
    TABLES
      creditexposure = lt_ccdetail.

  READ TABLE lt_ccdetail INTO ls_ccdetail INDEX 1.
  IF sy-subrc = 0.
    cv_open = ls_ccdetail-openvalue.
  ENDIF.

ENDFORM.

*&---------------------------------------------------------------------*
*&      Form  display_list
*&---------------------------------------------------------------------*
*&      Prints the classic list output.
*&---------------------------------------------------------------------*
FORM display_list.

  DATA: lv_matnr_disp TYPE c LENGTH 18.

  FORMAT COLOR COL_HEADING.
  WRITE: / 'Open Sales Order Margin Cockpit - Sales Org', p_vkorg.
  ULINE.
  WRITE: /1  'Order',
          12 'Item',
          20 'Customer',
          32 'Material',
          53 'Description',
          95 'Qty',
         110 'Net Value',
         128 'Margin',
         145 'Margin %',
         158 'GStat',
         166 'Credit'.
  ULINE.

  FORMAT COLOR COL_NORMAL.
  LOOP AT gt_out INTO gs_out.

    lv_matnr_disp = gs_out-matnr+0(18).

    WRITE: /1  gs_out-vbeln,
            12 gs_out-posnr,
            20 gs_out-kunnr,
            32 lv_matnr_disp,
            53 gs_out-maktx,
            95 gs_out-kwmeng,
           110 gs_out-netwr,
           128 gs_out-margin,
           145 gs_out-margin_pct,
           158 gs_out-gbstk,
           166 gs_out-credit_ok.

  ENDLOOP.

  ULINE.
  FORMAT COLOR COL_TOTAL.
  WRITE: /1 'Total items :', gv_count,
         /1 'Total value :', gv_total_netwr,
         /1 'Total margin:', gv_total_marg.

ENDFORM.
