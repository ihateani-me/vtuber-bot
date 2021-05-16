import asyncio
import logging
import typing as t

import aiohttp


vtuberlive_gql = r"""query($cursor:String) {
    vtuber {
        live(cursor:$cursor,limit:100) {
            _total
            items {
                id
                room_id
                title
                thumbnail
                timeData {
                    startTime
                }
                group
                channel {
                    id
                    name
                    image
                }
                platform
                is_premiere
                is_member
            }
            pageInfo {
                nextCursor
                hasNextPage
            }
        }
    }
}
"""

vtuberupcoming_gql = r"""query($cursor:String) {
    vtuber {
        upcoming(cursor:$cursor,limit:100) {
            _total
            items {
                id
                room_id
                title
                group
                timeData {
                    startTime
                }
                channel {
                    id
                    name
                    en_name
                }
                is_member
                is_premiere
                platform
            }
            pageInfo {
                nextCursor
                hasNextPage
            }
        }
    }
}
"""


class ihateanimeAPIV2:

    BASE_PATH = "https://api.ihateani.me/v2/"

    def __init__(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.logger = logging.getLogger("vtutils.ihateanime.ihateanimeAPIV2")
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "Listeners/1.0"}, loop=loop
        )

    async def close(self):
        """Close sessions"""
        await self.session.close()

    async def _post_gql(self, endpoint: str, payload: dict):
        url = self.BASE_PATH + endpoint
        async with self.session.post(url, json=payload) as resp:
            if "application/json" not in resp.headers["Content-Type"]:
                raise ValueError("Not poggers.")
            res = await resp.json()
            if "error" in res or "errors" in res:
                raise ValueError("Failed to fetch data, ignoring...")
        return res["data"]

    def _sort_by_time(self, dataset: list):
        dataset.sort(key=lambda x: x["timeData"]["startTime"])
        return dataset

    async def paginate_through(
        self, query_params: str, next_page_cursor: str = "", req_type: str = "live"
    ) -> t.Tuple[t.List[dict], bool]:
        collect_throughout = []
        total_real_data = -1
        incomplete_data = False
        while True:
            data_to_sent = {
                "query": query_params,
                "variables": {
                    "cursor": next_page_cursor
                }
            }
            try:
                req = await self._post_gql("graphql", data_to_sent)
                live_result = req["vtuber"][req_type]
                items = live_result["items"]
                collect_throughout.extend(items)
                if total_real_data == -1:
                    total_real_data = live_result["_total"]
                pageinfo = live_result["pageInfo"]
                if not pageinfo["hasNextPage"] or not pageinfo["nextCursor"]:
                    break
                next_page_cursor = pageinfo["nextCursor"]
            except ValueError as ve:
                self.logger.error(f"Traceback: {str(ve)}")
                self.logger.error("error occured, stopping pagination process.")
                self.logger.error(f"total data should be: {total_real_data}, got {len(collect_throughout)}")
                incomplete_data = True
                break
        return collect_throughout, incomplete_data

    async def fetch_lives(self) -> t.List[dict]:
        """
        This will fetch all lives that are currently running.
        """
        final_results, is_incomplete = await self.paginate_through(vtuberlive_gql)
        if is_incomplete:
            raise ValueError("Failed to get all data, ignoring...")
        final_results = self._sort_by_time(final_results)
        return final_results

    async def fetch_upcoming(self) -> t.List[dict]:
        final_results, _ = await self.paginate_through(vtuberupcoming_gql, "", "upcoming")
        final_results = self._sort_by_time(final_results)
        return final_results
