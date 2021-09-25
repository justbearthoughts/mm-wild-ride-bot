import re
import os
import requests
import argparse
import pandas as pd
import yfinance as yf
from sys import exit, argv, stderr
import matplotlib.pyplot as plt
from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta

# Dataframe override
pd.set_option('display.float_format', lambda x: '%.5f' % x)
pd.set_option('display.expand_frame_repr', False)

class ShortedStock():

    def __init__(self):
        pass

    def run(self, seekback: int, ticker:str):
        data = pd.DataFrame()
        regex = re.compile(f'(.*\|{ticker}\|.*)')
        start_date = date.today() + relativedelta(months=-seekback)
        end_date = datetime.now().date()

        stock = yf.Ticker(ticker)
        hist = stock.history(period=f'{seekback + 1}mo')

        if not os.path.exists('./finra_data/'):
            os.mkdir(os.path.join('.', 'finra_data'))

        for single_date in self.daterange(start_date, end_date):
            if not os.path.exists(f'./finra_data/CNMSshvol{single_date.strftime("%Y%m%d")}.txt'):
                try:
                    r = requests.get(f'http://regsho.finra.org/CNMSshvol{single_date.strftime("%Y%m%d")}.txt').text
                    res = regex.search(r).group(0)
                    df = pd.DataFrame({'Date': datetime.strptime(res.split("|")[0], '%Y%m%d').date(),'Symbol': res.split("|")[1],'ShortVolume': int(res.split("|")[2]),'ShortExemptVolume': int(res.split("|")[3]), 'TotalVolume': int(res.split("|")[4]), 'Market': res.split("|")[5].rstrip()}, index=[0])
                    data = data.append(df)
                    
                    with open(f'./finra_data/CNMSshvol{single_date.strftime("%Y%m%d")}.txt', 'w+') as f:
                        f.writelines(r)
                except:
                    pass
            else:
                with open(f'./finra_data/CNMSshvol{single_date.strftime("%Y%m%d")}.txt', 'r') as f:
                    res = regex.search(f.read()).group(0)
                    df = pd.DataFrame({'Date': datetime.strptime(res.split("|")[0], '%Y%m%d').date(),'Symbol': res.split("|")[1],'ShortVolume': int(res.split("|")[2]),'ShortExemptVolume': int(res.split("|")[3]), 'TotalVolume': int(res.split("|")[4]), 'Market': res.split("|")[5].rstrip()}, index=[0])
                    data = data.append(df)

        data['Date'] = pd.to_datetime(data['Date'])
        data = data.drop(['Symbol'], axis=1)
        hist.index = pd.to_datetime(hist.index)
        hist = hist.drop(['High', 'Low', 'Volume'], axis=1)

        data = pd.merge(data, hist, on='Date', how='outer').dropna()

        percentageVolShort = []
        for _, row in data.iterrows():
            percentageVolShort.append(((row['ShortVolume'] + row['ShortExemptVolume']) / row['TotalVolume']) * 100)
        data['Pct. of Volume short'] = percentageVolShort

        with pd.option_context('display.max_rows', None, 'display.max_columns', None):
            data = data.drop(['Market', 'Dividends', 'Stock Splits'], axis=1)
            data = data.set_index('Date')
            return data


    def daterange(self, start_date, end_date):
        for n in range(int((end_date - start_date).days)):
            yield start_date + timedelta(n)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='ShortedStock')
    parser.add_argument('--seekback', type=int, help='Months to seek back', required=True)
    parser.add_argument('--ticker', type=str, help='Ticker code', required=True)
    parser.add_argument('--print', action='store_true', help='Print data to stdout')
    parser.add_argument('--print-only', action='store_true', help='Only print, not graph')
    parser.add_argument('--float', action='store_true', help='Plot and calculate theoretical float')
    parser.add_argument('--float-pct', type=float, help='Percentage of volume that close short (example: 0.75)')


    if len(argv) == 1:
        parser.print_help(stderr)
        exit(1)

    args = parser.parse_args()

    if args.float and not args.float_pct:
        if args.float_pct <= 0:
            args.float_pct = args.float_pct
        else:
            args.float_pct = 0.75
    
    if args.float_pct and not args.float:
        args.float = True

    ShortedStock(int(args.seekback), str(args.ticker).upper())
