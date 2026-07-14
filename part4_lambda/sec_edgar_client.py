import requests

def _month_to_fiscal_quarter(report_month, fiscal_year_end_month):
        # fiscal year starts the month right after it ends
        fiscal_start_month = (fiscal_year_end_month % 12) + 1
        # how many months after fiscal start does this report month fall?
        months_since_start = (report_month - fiscal_start_month) % 12
        quarter = months_since_start // 3 + 1
        return f"Q{quarter}"

class SecEdgar:

    # ---MODULE 3---
    def __init__(self, fileurl): # runs automatically when you create a SecEdgar object
        self.fileurl = fileurl # stores the URL so other methods can use it
        self.name_dict = {} # empty dict: will hold title (from CIK data)
        self.ticker_dict = {} # empty dict: will hold ticker (from CIK data)
        # __init__ is Python's reserved name for "run this automatically when the object is created."
        # self refers to the specific instance of the class.
        # analogy: imagine the SecEdgar class is a cookie cutter, and each SecEdgar object you create is an individual cookie:
        # full analogy mapped out:
        #   cookie cutter = SecEdgar class (the blueprint)
        #   cookie = se (the object, the living thing in memory)
        #   recipe step = __init__ (what happens when you bake it)
        #   raw ingredients = the JSON file from SEC (external data you fetch)
        #   finished ingredients, organized = self.name_dict and self.ticker_dict (what you do with that raw data)
        #   asking the cookie something = se.name_to_cik("APPLE INC.")

        headers = {'user-agent': 'MLT MM muhsinmohamed2005@gmail.com'} # ID card we show the SEC (line 9)
        r = requests.get(self.fileurl, headers=headers) # actually fetches the JSON file

        self.filejson = r.json() # converts raw response into Python-readable JSON

        self.cik_json_to_dict() # immediately calls the method below to populate the dicts

    def cik_json_to_dict(self): # parses the JSON and fills both dictionaries
        self.name_dict = {}
        self.ticker_dict = {}
        # redundant with __init__, but resets them cleanly (intentional defensive programming)
        # If someone calls cik_json_to_dict() a second time (w/o calling the whole SecEdgar class), those lines wipe the old dictionaries clean before repopulating.
        # Without them, you'd be adding to existing data rather than replacing it, which could cause duplicates or stale entries.

        for key, value in self.filejson.items():
            self.name_dict[value['title']] = (value['cik_str'], value['title'], value['ticker'])
            self.ticker_dict[value['ticker']] = (value['cik_str'], value['title'], value['ticker'])
            # before the loop — self.filejson (raw SEC format): {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, "1": {...}}
            # to find Apple you'd have to guess the key is "0" — useless.
            # after the loop — self.name_dict (your format): {"APPLE INC.": (320193, "APPLE INC.", "AAPL"), "MICROSOFT CORP": (...), ...}
            # now you can look up any company instantly by name.
            # (same logic for self.ticker_dict).

    def name_to_cik(self, company_name):
        return self.name_dict.get(company_name)
        # company_name is just whatever string you pass in as the search term.
        # The method then uses .get() to look for that string as a key in self.name_dict, which is 'title' (synonymous with company_name).

    def ticker_to_cik(self, ticker):
        return self.ticker_dict.get(ticker)
        # (same logic as the 'name_to_cik' method).
    
    # ---MODULE 6---
    def _build_document_url(self, cik, accession_number, primary_document): # this is a private helper method focused on constructing the 10-Q/10-K document URL
        stripped_accession_number = accession_number.replace('-','') # dashes are stripped in the document URL
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{stripped_accession_number}/{primary_document}"
    
    def quarterly_filing(self, cik, year, quarter):
        """
    NOTE: `year` is expected to match the filing's REPORT DATE calendar year,
    not necessarily the company's own fiscal year label. For companies whose
    fiscal year doesn't align with the calendar year (e.g. Microsoft), the
    caller may need to pass the calendar year in which the desired fiscal
    quarter's END DATE actually falls, not the fiscal year number itself.
        """
        # step 1: pad CIK to 10 digits and build the URL
        padded_cik = str(cik).zfill(10) # zfill adds leading zeros to reach 10-digits
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        headers = {'user-agent': 'MLT MM muhsinmohamed2005@gmail.com'}
        r = requests.get(url, headers=headers)
        cik_specific_json = r.json() # building the JSON file for company-specific data
        fiscal_year_end_month = int(cik_specific_json['fiscalYearEnd'][:2])
        recent = cik_specific_json['filings']['recent'] # drilling down in the nested dictionary to the object that contains the data we're interested in (recent)
        forms = recent['form'] # holds the actual form values from the 'form' array)
        for i, form in enumerate(forms): # 'enumerate(forms)' gives you both the index (i) AND the value (form) at the same time.
            if form == '10-Q':
                report_year = recent['reportDate'][i][:4] # grabbing date at the same index; slices just the year (e.g., "2026" from "2026-03-30")
                if report_year == str(year):
                    report_month = int(recent['reportDate'][i][5:7])
                    report_quarter = _month_to_fiscal_quarter(report_month, fiscal_year_end_month)
                    if report_quarter == str(quarter):
                        return self._build_document_url(cik, recent['accessionNumber'][i], recent['primaryDocument'][i]) # generates the company-specific 10-Q document URL for the requested year and quarter.
                        # i tracks the current position across all parallel arrays simultaneously.
                        # when all conditions match, i points to the correct filing in every array;
                        # accessionNumber, primaryDocument, etc. are all guaranteed to belong to the same filing.
        return None # no matching filing found for the given year and quarter.
    
    def annual_filing(self, cik, year):
        padded_cik = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        headers = {'user-agent': 'MLT MM muhsinmohamed2005@gmail.com'}
        r = requests.get(url, headers=headers)
        cik_specific_json = r.json()
        recent = cik_specific_json['filings']['recent']
        forms = recent['form']
        for i, form in enumerate(forms):
            if form == '10-K':
                report_year = recent['reportDate'][i][:4]
                if report_year == str(year):
                    return self._build_document_url(cik, recent['accessionNumber'][i], recent['primaryDocument'][i])
        return None
