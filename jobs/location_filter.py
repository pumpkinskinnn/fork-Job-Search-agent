"""Keep UK roles; London/hybrid/UK remote priority is applied by scoring."""

import re

from config import FILTER_BY_LOCATION

_UK = re.compile(r"\b(?:UK|U\.?K\.?|United Kingdom|Great Britain|England|Scotland|Wales|Northern Ireland|GB|GBR)\b", re.I)
_UK_CITY = re.compile(
    r"\b(?:London|Greater London|Reading|Oxford|Cambridge|Slough|Guildford|Watford|"
    r"Croydon|Bromley|Richmond|Hounslow|Uxbridge|St Albans|Milton Keynes|Bristol|"
    r"Manchester|Birmingham|Leeds|Sheffield|Nottingham|Edinburgh|Glasgow|Cardiff|Belfast)\b", re.I
)
_FOREIGN_COUNTRY = re.compile(
    r"\b(?:US|USA|United States|Canada|Australia|New Zealand|India|Germany|France|"
    r"Ireland|Netherlands|Singapore|China|Japan|Spain|Italy|Belgium|Sweden|Switzerland|"
    r"Ontario|Connecticut)\b", re.I
)


def location_needs_description(job: dict) -> bool:
    location = job.get("location") or ""
    return bool(not _UK.search(location) and not _FOREIGN_COUNTRY.search(location)
                and re.search(r"\b(?:remote|hybrid|global|worldwide|EMEA|Europe|multiple)\b", location, re.I))


def location_matches(job: dict) -> bool:
    if not FILTER_BY_LOCATION:
        return True
    location = (job.get("location") or "").strip()
    if not location or re.fullmatch(r"\d+\s+locations", location, re.I):
        return True
    if _UK.search(location):
        return True
    if _FOREIGN_COUNTRY.search(location):
        return False
    if _UK_CITY.search(location):
        return True
    if re.search(r"\b(?:remote|hybrid|global|worldwide|EMEA|Europe|multiple)\b", location, re.I):
        description = job.get("description") or ""
        return bool(re.search(r"\b(?:UK|United Kingdom)\b.{0,50}\b(?:remote|based|eligible)\b|"
                              r"\b(?:remote|based|eligible)\b.{0,50}\b(?:UK|United Kingdom)\b", description, re.I))
    return False
