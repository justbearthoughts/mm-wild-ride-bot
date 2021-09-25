from collections import Counter
from io import BytesIO
import math
from PIL import Image
import asyncpraw
import asyncio
import os
import json
import discord
import traceback
from urllib.error import HTTPError
import pytesseract
import yfinance as yf
import asyncprawcore
import requests
import re
from datetime import datetime
from discord.ext import commands
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import FirefoxOptions
from time import sleep
from nltk.sentiment import SentimentIntensityAnalyzer
import nltk
from asyncpraw.models import MoreComments

import os

import rsi
import shortedStock

import config

BOT_VERSION = '0.2.0'

nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('maxent_ne_chunker')
nltk.download('words')
nltk.download('vader_lexicon')

sia = SentimentIntensityAnalyzer()

tickerRE = re.compile(r"(?:\s)?([A-Z]{2,5})(?![a-z’'\.]+)(?:\s)?")

discord_token = config.discord_token
tmp = {}

if not os.path.exists('./playtracker.json'):
    with open('playtracker.json', 'w') as outfile:
        json.dump(tmp, outfile)

if not os.path.exists('./bannedusers.json'):
    with open('bannedusers.json', 'w') as outfile:
        tmp['banned'] = []
        json.dump(tmp, outfile)

if not os.path.exists('./bannedtickers.json'):
    with open('bannedtickers.json', 'w') as outfile:
        tmp['banned'] = []
        json.dump(tmp, outfile)

if not os.path.exists('./visualmod.md'):
    with open('visualmod.md', 'w') as outfile:
        json.dump(tmp, outfile)

if not os.path.exists('./visualmod.md'):
    with open('visualmod.md', 'w') as outfile:
        pass
bot = commands.Bot(command_prefix='$')

reddit = asyncpraw.Reddit(
    client_id=config.client_id,
    client_secret=config.client_secret,
    password=config.passwd,
    username=config.username,
    user_agent=f'Yolo (by u/{config.username})'
)
reddit.read_only = True

async def postMsg(msg):
    await bot.get_channel(855609062892765236).send(msg)
    
async def getSentiment(submission):
    senti = {'good': 0, 'bad': 0, 'neutral': 0}
    sub = await reddit.submission(id=submission)
    comments = await sub.comments()
    for comment in comments:
        if isinstance(comment, MoreComments):
            continue
        sentiment = sia.polarity_scores(comment.body)
        if sentiment['compound'] > 0:
            senti['good'] += 1
        elif sentiment['neu'] > 0:
            senti['neutral'] += 1
        else:
            senti['bad'] +=1
    return senti

async def getPost(submission):
    try:
        options = FirefoxOptions()
        options.headless = True
        browser = webdriver.Firefox(options=options)
        browser.maximize_window()
        browser.get(f'https://www.reddit.com{submission.permalink}')
        element = browser.find_element('xpath', '//div[@data-test-id="post-content"]')
        location = element.location
        size = element.size
        total_height = element.size["height"]+1000
        browser.set_window_size(1920, total_height)
        sleep(1)
        png = browser.get_screenshot_as_png()
        img = Image.open(BytesIO(png))
        browser.quit()
        arr = BytesIO()
        img.save(arr, format='PNG')
        arr.seek(0)

        left = location['x'] + 270
        top = location['y']
        right = location['x'] + 270 + size['width']
        bottom = location['y'] + size['height']

        img = img.crop((math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)))

        custom_conf = r'--oem 3 --psm 6'
        content = pytesseract.image_to_string(img, config=custom_conf)
        pic = discord.File(arr, f'{submission}.png')
    except NoSuchElementException:
        return None
    return content, pic

async def checkTimer(submission):
    await asyncio.sleep(300)
    retest = await reddit.submission(submission)
    if retest.selftext == '[removed]':
        print(f'{datetime.now()} - Stop timer for {submission.title} - Discarded.')         
    else:
        print(f'{datetime.now()} - Stop timer for {submission.title} - Posting.')
        chain = 'N/A'
        stock = 'N/A'
        data2 = 'N/A'
        data = {}
        data2 = {}
        chain_track = ''
        likely_ticker = ''
        try:
            content, pic = await getPost(submission)
            if content == None:
                await postMsg(f'Error occurred while getting image. Please verify this manually. Permalink: https://www.reddit.com{submission.permalink}')
                return
            elif len(content) < 1000:
                await postMsg(f'DD too short. Length determined by OCR: {len(content)}. Permalink: https://www.reddit.com{submission.permalink}')
                return

            tickers = tickerRE.findall(content)
            tickers += tickerRE.findall(str(submission.title).upper())

            counters = Counter(list(filter(lambda x: x != 'DD', tickers)))
            most = counters.most_common(5)
            for ticker in most:
                try:
                    print(ticker)
                    stock = yf.Ticker(ticker[0])
                    _ = stock.info['regularMarketOpen']
                    likely_ticker = ticker[0]
                    break
                except (KeyError, ValueError, HTTPError, IndexError):
                    continue
            print(likely_ticker)
            try:
                chain = stock.options[0:3]
                response = f'\n```Snippet of Options Chain for {str(likely_ticker).upper()}\n'
                
                for item in chain:
                    response += f'EXP: {item}\n{stock.option_chain(item)[0].loc[:, ~stock.option_chain(item)[0].columns.isin(["contractSymbol", "lastTradeDate", "contractSize", "currency", "change", "percentChange"])].loc[stock.option_chain(item)[0]["inTheMoney"] == False].head(3)}\n'
                    chain_track += f'{stock.option_chain(item)[0].loc[:, ~stock.option_chain(item)[0].columns.isin(["contractSymbol", "lastTradeDate", "contractSize", "currency", "change", "percentChange"])].loc[stock.option_chain(item)[0]["inTheMoney"] == False].head(3)}\n'
            except IndexError:
                response = f'\n```No Options Chain for {str(likely_ticker).upper()}\n'

            url = f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={likely_ticker}'
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'})
            try:
                data = json.loads(res.text)['quoteResponse']['result'][0]
            except KeyError:
                data = data

            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{likely_ticker}?region=US&lang=en-US&includePrePost=false&interval=2m&useYfid=true&range=1d&corsDomain=finance.yahoo.com&.tsrc=finance'
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'})
            data2 = json.loads(res.text)

        except IndexError:
            response = '\n```\nError getting info on the ticker: Unsupported format.\n'
            print(traceback.format_exc())
        with open('playtracker.json', 'r') as infile:
            playtrack = json.load(infile)
        try:
            last_traded = data["regularMarketPrice"] if "regularMarketPrice" in data.keys() else "N/A"
        except KeyError:
            last_traded = "N/A"
        try:
            volume_last = stock.info["volume"] if isinstance(stock, yf.Ticker) else stock
        except (KeyError, HTTPError):
            volume_last = "N/A"
        try:
            vol_10_avg = stock.info["averageVolume10days"] if isinstance(stock, yf.Ticker) else stock
        except (KeyError, HTTPError):
            vol_10_avg = "N/A"
        try:
            total = data2["chart"]["result"][0]["indicators"]["quote"][0]["volume"]
            last10 = data2["chart"]["result"][0]["indicators"]["quote"][0]["volume"][-10:]
            total = [0 if i is None else i for i in total]
            last10 = [0 if i is None else i for i in last10]

            avgTot = round(float(sum(total) / len(total)), 1)
            avg10 = round(float(sum(last10) / len(last10)), 1)
        except (KeyError, IndexError):
            avgTot = "N/A"
            avg10 = "N/A"
        
        response += f'\nLast traded price:' + f'{last_traded : >15}'
        response += f'\nVolume last day:' + f'{volume_last : >17}'
        response += f'\nVolume 10d avg.:' + f'{vol_10_avg : >17}'
        response += f'\nAverage volume on day:' + f'{avgTot : >11}'
        response += f'\nAverage volume last 10:' + f'{avg10 : >10}'
        response += '```'

        try:
            if likely_ticker != '':
                try:
                    with open('bannedtickers.json', 'r') as infile:
                        tmp = json.load(infile)
                        if likely_ticker in tmp['banned']:
                            await postMsg(f'Discarded https://www.reddit.com{submission.permalink} as ticker is banned')
                            return
                except json.decoder.JSONDecodeError:
                    pass
                if stock.info["volume"] > stock.info["averageVolume10days"] and avg10 > avgTot:
                    response += f'\n\nThis play has high volume on the day and into close compared to the norm. This is a candidate for a play. Please check Options Flow @everyone'
            else:
                response += 'Could not determine ticker - posting to be safe.'
            
            await postMsg(f'@everyone \nBy u/{submission.author}\nTicker estimated to be: {likely_ticker} - please verify.\nNB: Testing sentiment on comments:\n```{await getSentiment(submission)}\nUpvotes: {retest.score}\nUpvote Ratio: {retest.upvote_ratio}\nComments: {retest.num_comments}\n```\nhttps://www.reddit.com/r/wallstreetbets/comments/{submission}\n{submission.title}{response}')
            await bot.get_channel(854087011987226624).send(file=pic)
        except AttributeError:
            pass


async def streamer(sub):
    sub = await reddit.subreddit(sub)
    async for submission in sub.stream.submissions(skip_existing=True):
        try:
            if submission.link_flair_text == 'DD':
                print(f'{datetime.now()} - Start timer for {submission.title}')
                asyncio.create_task(checkTimer(submission))

        except (asyncprawcore.exceptions.RequestException, asyncio.exceptions.TimeoutError):
            await bot.get_channel(854251957152383007).send(f'{datetime.now()} - Error on {submission.id} {submission.title}\n```{traceback.format_exc()}```\n<@510951917128646657> fix your shitty code.')
            continue

@bot.command(
    name='finraData',
    help='Get finra short volume data for supplied ticker'
)
async def finraData(ctx, arg):
    stockData = shortedStock.ShortedStock().run(1, str(arg).upper())
    await ctx.send(f'Data for {str(arg).upper()}:\n```{stockData.tail(10)}```')

@bot.command(
    name='getRSI',
    help='Get RSI of a supplied stock'
)
async def getRSI(ctx, *args):
    periods = ['max', '1mo', '2mo', '3mo', '6mo', '1y']
    if args[1] not in periods:
        await ctx.send(f'Please choose a proper period format. Proper format is: {periods}')
        return
    await ctx.send(f'```{rsi.run(args[0], args[1])}```')

@bot.command(
    name='gainers',
    help='Get top gainers on the day'
)
async def gainers(ctx):
    options = FirefoxOptions()
    options.headless = True
    browser = webdriver.Firefox(options=options)
    browser.maximize_window()
    browser.get('https://finance.yahoo.com/gainers')
    sleep(5)
    btn = browser.find_element_by_xpath('//*[@id="consent-page"]/div/div/div/form/div[2]/div[2]/button')
    btn.click()
    sleep(5)
    element = browser.find_element('xpath', '//div[@id="fin-scr-res-table"]')
    location = element.location
    size = element.size
    total_height = element.size["height"]+1000
    browser.set_window_size(1920, total_height)
    sleep(1)
    png = browser.get_screenshot_as_png()
    img = Image.open(BytesIO(png))
    browser.quit()
    arr = BytesIO()
    img.save(arr, format='PNG')
    arr.seek(0)

    left = location['x'] + 270
    top = location['y']
    right = location['x'] + 290 + size['width']
    bottom = location['y'] + size['height']

    img = img.crop((math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)))
    picture = discord.File(arr, 'gainers.png')
    await ctx.send(file=picture)


@bot.command(
    name='finra',
    help='Get URL for Finra-Markets data on the stock.'
)
async def finra(ctx, arg):
    url = f'https://finra-markets.morningstar.com/MarketData/EquityOptions/detail.jsp?query={arg}'
    await ctx.send(url)
    
@bot.command(
    name='options',
    help='List top 4 OTM/ATM call options for next 3 expiries for the supplied ticker.\tExample: $options AAPL'
)
async def options(ctx, arg):
    stock = yf.Ticker(arg)
    try:
        chain = stock.options[0:3]
        response = f'Snippet of Options Chain for {str(arg).upper()}\n```'
        for item in chain:
            response += f'EXP: {item}\n{stock.option_chain(item)[0].loc[:, ~stock.option_chain(item)[0].columns.isin(["contractSymbol", "lastTradeDate", "contractSize", "currency", "change", "percentChange"])].loc[stock.option_chain(item)[0]["inTheMoney"] == False].head(4)}\n'
        response += '```'
    except IndexError:
        response = f'No Options Chain for {str(arg).upper()}\n```'
    await ctx.send(response)

@bot.command(
    name='version',
    help='Show version of the bot'
)
async def version(ctx):
    await ctx.send(f'Bot version: {BOT_VERSION}')

@bot.command(
    name='playInfo',
    help='Query needed info for determining a play.'
)
async def playInfo(ctx, arg):
    stock = yf.Ticker(arg)

    try:
        chain = stock.options[0:3]
        response = f'```Snippet of Options Chain for {str(arg).upper()}\n'
        for item in chain:
            response += f'EXP: {item}\n{stock.option_chain(item)[0].loc[:, ~stock.option_chain(item)[0].columns.isin(["contractSymbol", "lastTradeDate", "contractSize", "currency", "change", "percentChange"])].loc[stock.option_chain(item)[0]["inTheMoney"] == False].head(4)}\n'
    except IndexError:
        response = f'```No Options Chain for {str(arg).upper()}\n'
  
    try:
        url = f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={arg}'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'})
        data = json.loads(res.text)['quoteResponse']['result'][0]

        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{arg}?region=US&lang=en-US&includePrePost=false&interval=2m&useYfid=true&range=1d&corsDomain=finance.yahoo.com&.tsrc=finance'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'})
        data2 = json.loads(res.text)
        try:
            last_traded = data["regularMarketPrice"] if "regularMarketPrice" in data.keys() else "N/A"
        except KeyError:
            last_traded = "N/A"
        try:
            volume_last = stock.info["volume"] if isinstance(stock, yf.Ticker) else stock
        except KeyError:
            volume_last = "N/A"
        try:
            vol_10_avg = stock.info["averageVolume10days"] if isinstance(stock, yf.Ticker) else stock
        except KeyError:
            vol_10_avg = "N/A"
        try:
            total = data2["chart"]["result"][0]["indicators"]["quote"][0]["volume"]
            last10 = data2["chart"]["result"][0]["indicators"]["quote"][0]["volume"][-10:]
            total = [0 if i is None else i for i in total]
            last10 = [0 if i is None else i for i in last10]

            avgTot = round(float(sum(total) / len(total)), 1)
            avg10 = round(float(sum(last10) / len(last10)), 1)
        except KeyError:
            avgTot = "N/A"
            avg10 = "N/A"
        
        response += f'\nLast traded price:' + f'{last_traded : >15}'
        response += f'\nVolume last day:' + f'{volume_last : >17}'
        response += f'\nVolume 10d avg.:' + f'{vol_10_avg : >17}'
        response += f'\nAverage volume on day:' + f'{avgTot : >11}'
        response += f'\nAverage volume last 10:' + f'{avg10 : >10}'   
        response += '```'
        try:
            if stock.info["volume"] > stock.info["averageVolume10days"] and avg10 > avgTot:
                response += f'\n\nThis play has high volume on the day and into close compared to the norm. This is a candidate for a play. Please check Options Flow'
        except AttributeError:
            pass
        response += f'\nApe tracker (https://wsbtrackers.com/Stocks/{str(arg).upper()}.html):\n'
        
        try:
            options = FirefoxOptions()
            options.headless = True
            browser = webdriver.Firefox(options=options)
            browser.maximize_window()
            browser.get(f'https://wsbtrackers.com/Stocks/{str(arg).upper()}.html')
            element = browser.find_element('xpath', '//body')
            total_height = element.size["height"]+1000
            browser.set_window_size(1920, total_height)
            sleep(1)
            png = browser.get_screenshot_as_png()
            browser.quit()
            img = Image.open(BytesIO(png))
            arr = BytesIO()
            img.save(arr, format='PNG')
            arr.seek(0)
            picture = discord.File(arr, 'apes.png')
        except NoSuchElementException:
            picture = None

        for item in list(response[0+i:1990+i] for i in range(0, len(response), 1990)):
            await ctx.send(item)
        if picture:
            await ctx.send(file=picture)
        else:
            await ctx.send(f'Error occured while getting image. Please try again later - Reddit CDN might be down.')
    except (HTTPError, IndexError, KeyError) as err:
        await ctx.send(f'Error occurred while retrieving information on {str(arg).upper()}:\n```{traceback.format_exc()}```\n<@510951917128646657> fix your shitty code.')

@bot.command(
    name='queryPost',
    help='Query a post on WSB for popularity.\tExample: $queryPost o08lpj'
)
async def queryPost(ctx, arg):
    try:
        query = await reddit.submission(arg)
        response = f'```NB: Testing sentiment on comments:\n{await getSentiment(query)}\n\nUpvotes: {query.score}\nUpvote Ratio: {query.upvote_ratio}\nComments: {query.num_comments}\n```\nPermalink: https://www.reddit.com{query.permalink}\n'
        content, picture = await getPost(query)
        if content == None:
            await ctx.send(f'Error occured while getting image. Please try again later - Reddit CDN might be down.')
            return
        
        await ctx.send(response)
        await ctx.send(file=picture)
    except asyncprawcore.exceptions.NotFound:
        await ctx.send(f'```\nPost with ID: "{arg}" not found\n```')

@bot.command(
    name='stockInfo',
    help='Get statistics of the stock.'
)
async def stockInfo(ctx, arg):
    try:
        stock = yf.Ticker(arg)
        await ctx.send(f'```\n{str(arg).upper()}:\nAverage Vol.: {stock.info["averageDailyVolume10Day"]}\nVolume: {stock.info["volume"]}\nLast Close: {stock.info["previousClose"]}\nLast open: {stock.info["regularMarketOpen"]}\nMarket cap: {stock.info["marketCap"]}\nShares short: {stock.info["sharesShort"] if stock.info["sharesShort"] is not None else "N/A"}\n% Float short: {round(float(stock.info["shortPercentOfFloat"])*100, 2) if stock.info["shortPercentOfFloat"] is not None else "N/A"}%\nYTD Change: {round(float(stock.info["52WeekChange"])*100, 2)}%\n```')
    except ValueError:
        await ctx.send(f'Couldn\'t get info on {str(arg).upper()}')

@bot.command(
    name='stockPrice',
    help='List stock price for supplied ticker'
)
async def stockPrice(ctx, arg):
    try:
        url = f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={arg}'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:86.0) Gecko/20100101 Firefox/86.0'})
        data = {}
        try:
            data = json.loads(res.text)['quoteResponse']['result'][0]
            try:
                if 'marketState' in data.keys():
                    if data['marketState'] == 'PRE':
                        await ctx.send(f'Latest PM price of {str(arg).upper()}: {data["preMarketPrice"]}, {round(float(data["preMarketChangePercent"]), 3)}%')
                    elif data['marketState'] == 'REGULAR':
                        await ctx.send(f'Latest price of {str(arg).upper()}: {data["regularMarketPrice"]}, {round(float(data["regularMarketChangePercent"]), 3)}%')
                    elif data['marketState'] == 'POST':
                        await ctx.send(f'Latest AH price of {str(arg).upper()}: {data["postMarketPrice"]}, {round(float(data["postMarketChangePercent"]), 3)}%')
                    else:
                        await ctx.send(f'Latest price of {str(arg).upper()}: {data["regularMarketPrice"]}, {round(float(data["regularMarketChangePercent"]), 3)}%')
                else:
                    try:
                        await ctx.send(f'{str(arg).upper()} last traded: {data["regularMarketPrice"]}, {round(float(data["regularMarketChangePercent"]), 3)}%')    
                    except KeyError:
                        await ctx.send(f'Error occurred while getting price of {str(arg).upper()}\n```{traceback.format_exc()}```\n<@510951917128646657> fix your shitty code.')
            except IndexError:
                await ctx.send(f'Error occurred while getting price of {str(arg).upper()}\n```{traceback.format_exc()}```\n<@510951917128646657> fix your shitty code.')
        except KeyError:
            await ctx.send(f'{str(arg).upper()} last traded: {data["regularMarketPrice"]}, {round(float(data["regularMarketChangePercent"]), 3)}%')
    except (TypeError, KeyError, IndexError) as err:
        await ctx.send(f'Couldn\'t get price of {str(arg).upper()}')

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))
    while True:
        try:
            await streamer('wallstreetbets')
        except (asyncprawcore.exceptions.RequestException, asyncprawcore.exceptions.ServerError, OSError):
            continue
        finally:
            reddit.close()

bot.run(discord_token)