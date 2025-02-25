import os
# from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from bs4 import BeautifulSoup
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 加载 .env 文件
# load_dotenv()

# 创建 OpenAI 客户端实例
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'), base_url=os.getenv('OPENAI_API_BASE'))

class Product:
    def __init__(self, id: str, name: str, tagline: str, description: str, votesCount: int, createdAt: str, featuredAt: str, website: str, url: str, **kwargs):
        self.name = name
        self.tagline = tagline
        self.description = description
        self.votes_count = votesCount
        self.created_at = self.convert_to_beijing_time(createdAt)
        self.featured = "是" if featuredAt else "否"
        self.website = website
        self.url = url
        self.og_image_url = self.fetch_og_image_url()
        self.keyword = self.generate_keywords()
        self.translated_tagline = self.translate_text(self.tagline)
        self.translated_description = self.translate_text(self.description)

    def fetch_og_image_url(self) -> str:
        """获取产品的Open Graph图片URL"""
        response = requests.get(self.url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 查找og:image meta标签
            og_image = soup.find("meta", property="og:image")
            if og_image:
                return og_image["content"]
            # 备用:查找twitter:image meta标签
            twitter_image = soup.find("meta", name="twitter:image")
            if twitter_image:
                return twitter_image["content"]
        return ""

    def generate_keywords(self) -> str:
        """生成产品的关键词，显示在一行，用逗号分隔"""
        prompt = f"根据以下内容生成适合的中文关键词，用英文逗号分隔开：\n\n产品名称：{self.name}\n\n标语：{self.tagline}\n\n描述：{self.description}"

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Generate suitable Chinese keywords based on the product information provided. The keywords should be separated by commas."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=50,
                temperature=0.7,
            )
            keywords = response.choices[0].message.content.strip()
            if ',' not in keywords:
                keywords = ', '.join(keywords.split())
            return keywords
        except Exception as e:
            print(f"Error occurred during keyword generation: {e}")
            return "无关键词"

    def translate_text(self, text: str) -> str:
        """使用OpenAI翻译文本内容"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "你是世界上最专业的翻译工具，擅长英文和中文互译。你是一位精通英文和中文的专业翻译，尤其擅长将IT公司黑话和专业词汇翻译成简洁易懂的地道表达。你的任务是将以下内容翻译成地道的中文，风格与科普杂志或日常对话相似。"},
                    {"role": "user", "content": text},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            translated_text = response.choices[0].message.content.strip()
            return translated_text
        except Exception as e:
            print(f"Error occurred during translation: {e}")
            return text

    def convert_to_beijing_time(self, utc_time_str: str) -> str:
        """将UTC时间转换为北京时间"""
        utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')
        beijing_tz = pytz.timezone('Asia/Shanghai')
        beijing_time = utc_time.replace(tzinfo=pytz.utc).astimezone(beijing_tz)
        return beijing_time.strftime('%Y年%m月%d日 %p%I:%M (北京时间)')

    def to_markdown(self, rank: int) -> str:
        """返回产品数据的Markdown格式"""
        og_image_markdown = f"![{self.name}]({self.og_image_url})"
        return (
            f"## [{rank}. {self.name}]({self.url})\n"
            f"**标语**：{self.translated_tagline}\n"
            f"**介绍**：{self.translated_description}\n"
            f"**产品网站**: [立即访问]({self.website})\n"
            f"**Product Hunt**: [View on Product Hunt]({self.url})\n\n"
            f"{og_image_markdown}\n\n"
            f"**关键词**：{self.keyword}\n"
            f"**票数**: 🔺{self.votes_count}\n"
            f"**是否精选**：{self.featured}\n"
            f"**发布时间**：{self.created_at}\n\n"
            f"---\n\n"
        )

def get_producthunt_token():
    """使用 developer token 进行认证"""
    token = os.getenv('PRODUCTHUNT_DEVELOPER_TOKEN')
    if not token:
        raise Exception("Product Hunt developer token not found in environment variables")
    return token

def fetch_product_hunt_data():
    """从Product Hunt获取前一天的Top 30数据"""
    token = get_producthunt_token()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = "https://api.producthunt.com/v2/api/graphql"

    # 添加更多请求头信息
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "DecohackBot/1.0 (https://decohack.com)",
        "Origin": "https://decohack.com",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Connection": "keep-alive"
    }

    # 设置重试策略
    retry_strategy = Retry(
        total=3,  # 最多重试3次
        backoff_factor=1,  # 重试间隔时间
        status_forcelist=[429, 500, 502, 503, 504]  # 需要重试的HTTP状态码
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)

    base_query = """
    {
      posts(order: VOTES, postedAfter: "%sT00:00:00Z", postedBefore: "%sT23:59:59Z", after: "%s") {
        nodes {
          id
          name
          tagline
          description
          votesCount
          createdAt
          featuredAt
          website
          url
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    all_posts = []
    has_next_page = True
    cursor = ""

    while has_next_page and len(all_posts) < 30:
        query = base_query % (date_str, date_str, cursor)
        try:
            response = session.post(url, headers=headers, json={"query": query})
            response.raise_for_status()  # 抛出非200状态码的异常
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            raise Exception(f"Failed to fetch data from Product Hunt: {e}")

        data = response.json()['data']['posts']
        posts = data['nodes']
        all_posts.extend(posts)

        has_next_page = data['pageInfo']['hasNextPage']
        cursor = data['pageInfo']['endCursor']

    # 只保留前30个产品
    return [Product(**post) for post in sorted(all_posts, key=lambda x: x['votesCount'], reverse=True)[:30]]

def generate_markdown(products, date_str):
    """生成Markdown内容并保存到data目录"""
    # 获取今天的日期并格式化
    today = datetime.now(timezone.utc)
    date_today = today.strftime('%Y-%m-%d')

    markdown_content = f"# PH今日热榜 | {date_today}\n\n"
    for rank, product in enumerate(products, 1):
        markdown_content += product.to_markdown(rank)

    # 确保 data 目录存在
    os.makedirs('data', exist_ok=True)

    # 修改文件保存路径到 data 目录
    file_name = f"data/producthunt-daily-{date_today}.md"

    # 如果文件存在，直接覆盖
    with open(file_name, 'w', encoding='utf-8') as file:
        file.write(markdown_content)
    print(f"文件 {file_name} 生成成功并已覆盖。")


def main():
    # 获取昨天的日期并格式化
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')

    # 获取Product Hunt数据
    products = fetch_product_hunt_data()

    # 生成Markdown文件
    generate_markdown(products, date_str)

if __name__ == "__main__":
    main()