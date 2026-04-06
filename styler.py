"""Google Sheets visual API styler."""
import gspread

def apply_tx_styling(sh: gspread.Spreadsheet, ws: gspread.Worksheet):
    """Freezes row 1 and applies conditional formatting."""
    ws.freeze(rows=1)
    
    # Conditional formatting via raw batch_update
    requests = [
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 3}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$B2="Доход"'}]
                        },
                        "format": {
                            "backgroundColor": {"red": 0.8, "green": 0.95, "blue": 0.8},
                            "textFormat": {"bold": True, "foregroundColor": {"red": 0.1, "green": 0.5, "blue": 0.1}}
                        }
                    }
                },
                "index": 0
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 3}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$B2="Расход"'}]
                        },
                        "format": {
                            "backgroundColor": {"red": 0.95, "green": 0.8, "blue": 0.8},
                            "textFormat": {"bold": True, "foregroundColor": {"red": 0.6, "green": 0.1, "blue": 0.1}}
                        }
                    }
                },
                "index": 1
            }
        },
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": 1, "endColumnIndex": 3}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$B2="Копилка"'}]
                        },
                        "format": {
                            "backgroundColor": {"red": 0.8, "green": 0.85, "blue": 0.95},
                            "textFormat": {"bold": True, "foregroundColor": {"red": 0.1, "green": 0.3, "blue": 0.6}}
                        }
                    }
                },
                "index": 2
            }
        }
    ]
    try:
        sh.batch_update({"requests": requests})
    except Exception as e:
        print(f"Error applying conditional styling: {e}")

def apply_dashboard_styling(sh: gspread.Spreadsheet, ws: gspread.Worksheet):
    """Sets up the Dashboard visually."""
    ws.freeze(rows=1)
    
    # 1. Update basic blocks layout
    layout = [
        ["📊 ФИНАНСОВЫЙ ДАШБОРД", "", "", "", "📅 Период:"],
        ["", "", "", "", ""],
        ["СЕГОДНЯШНИЕ ТРАТЫ", "", "СТАТУС БЮДЖЕТА", "", "ПОСЛЕДНИЕ ТРАНЗАКЦИИ"],
        ["", "", "Обязательное:", "", "Ожидание..."],
        ["", "", "Гулянки:", "", ""],
        ["", "", "Разовые:", "", ""],
        ["", "", "Копилка:", "", ""],
        ["", "", "", "", ""],
        ["ДИАГРАММА ПО ПЛАНУ", "", "СТРУКТУРА РАСХОДОВ", "", ""]
    ]
    # To prevent overwriting dynamically placed data, we only write headers safely.
    ws.update("A1:E9", layout)
    
    # 2. Format title
    ws.format("A1:B1", {
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.4},
        "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
    })
    
    # Block Headers
    header_format = {
        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
        "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2}},
        "borders": {"bottom": {"style": "SOLID", "width": 2, "color": {"red": 0, "green": 0, "blue": 0}}}
    }
    ws.format("A3:A3", header_format)
    ws.format("C3:C3", header_format)
    ws.format("E3:E3", header_format)
    ws.format("A9:A9", header_format)
    ws.format("C9:C9", header_format)
    
    # Resize columns for better look
    requests = [{
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": 1
            },
            "properties": {"pixelSize": 250},
            "fields": "pixelSize"
        }
    }, {
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 2,
                "endIndex": 3
            },
            "properties": {"pixelSize": 250},
            "fields": "pixelSize"
        }
    }, {
        "updateDimensionProperties": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": 4,
                "endIndex": 5
            },
            "properties": {"pixelSize": 350},
            "fields": "pixelSize"
        }
    }]
    try:
        sh.batch_update({"requests": requests})
    except Exception as e:
        print(f"Error applying dashboard UI: {e}")
