import mapadroid.utils.pluginBase
from flask import render_template, Blueprint
from mapadroid.madmin.functions import auth_required
import os
import time
import json
import sys
from threading import Thread
import itertools
import pickle
from math import sqrt, floor
from enum import Enum
import requests
from mapadroid.utils.logging import get_logger, LoggerEnums

def parseEnumProto(url, name):
    r = requests.get(url)
    enumDict = {}
    for line in r.iter_lines(decode_unicode=True):
        if not line.startswith("syntax") and not line.startswith("package") and "=" in line:
            enumDict[line.split("=")[0].strip()] = line.split("=")[1].replace(";", "").strip()
    return Enum(name, enumDict)

PokemonId = parseEnumProto("https://raw.githubusercontent.com/Furtif/POGOProtos/master/src/"
        "POGOProtos/Enums/PokemonId.proto", "PokemonId")
Form = parseEnumProto("https://raw.githubusercontent.com/Furtif/POGOProtos/master/src/"
        "POGOProtos/Enums/Form.proto", "Form")


class PvpBase():
    def __init__(self):
        with open("{}/cp_multipliers.json".format(os.path.dirname(os.path.abspath(__file__))), "r") as f:
            self.cp_multipliers = json.load(f)

    def __getstate__(self):
        d = self.__dict__.copy()
        if 'logger' in d:
            d['logger'] = "logger"
        return d

    def __setstate__(self, d):
        if 'logger' in d:
            d['logger'] = get_logger(LoggerEnums.plugin)
        self.__dict__.update(d)
        self.logger.debug4("{} object loaded from pickle file".format(type(self).__name__))


class Pokemon(PvpBase):
    def __init__(self, num: int, form: int, atk: int, de: int, sta: int,
            evolutions: list, ranklength: int):
        super(Pokemon, self).__init__()
        self.num = num
        self.form = form
        self.atk = atk
        self.de = de
        self.sta = sta
        self.evolutions = evolutions
        self.ranklength = ranklength
        self.logger = get_logger(LoggerEnums.plugin)


        self.products = {}
        self.greatPerfect, self.greatLowest = self._spreads(1500)
        self.ultraPerfect, self.ultraLowest = self._spreads(2500)
        self.logger.debug("Pokemon {}, form {} initialized".format(self.num, self.form))

    def num(self):
        return int(self.num)

    def form(self):
        return int(self.form)

    def ident(self):
        return str("{}-{}".format(self.num, self.form))

    def __str__(self):
        return "{{'num': {}, 'form': {}, 'atk': {}, 'de': {}, 'sta': {}, 'evolutions': {}}}".format(
            self.num, self.form, self.atk, self.de, self.sta, self.evolutions)

    def calculate_cp(self, atk, de, sta, lvl):
        lvl = str(lvl).replace(".0", "")
        cp = ((self.atk + atk) * sqrt(self.de + de) *
              sqrt(self.sta + sta) * (self.cp_multipliers[str(lvl)]**2)
              / 10)
        return int(cp)

    def max_cp(self):
        return self.calculate_cp(15, 15, 15, 40)

    def getEvolution(self):
        if self.evolutions:
            self.logger.debug("getEvolution returning {}".format(self.evolutions))
            return self.evolutions
        else:
            return False

    def pokemon_rating(self, limit, atk, de, sta, lvl):
        highest_rating = 0
        highest_cp = 0
        highest_level = 0
        highest_product = 0
        rank = 4096
        min_level = self.min_level(limit)
        max_level = min(self.max_level(limit), lvl)

        for level in range(int(min_level * 2), int((max_level + 0.5) * 2)):
            level = str(level / float(2)).replace(".0", "")
            cp = self.calculate_cp(atk, de, sta, level)
            if not cp > limit:
                attack = (self.atk + atk) * self.cp_multipliers[str(level)]
                defense = (self.de + de) * self.cp_multipliers[str(level)]
                stamina = int(((self.sta + sta) *
                               (self.cp_multipliers[str(level)])))
                product = attack * defense * stamina
                if product > highest_rating:
                    highest_rating = product
                    highest_cp = cp
                    highest_level = level
                    highest_product = product
        try:
            rank = self.products[limit].index(highest_product) + 1
        except:
            rank = 4096
        return highest_rating, highest_cp, highest_level, rank

    def max_level(self, limit):
        if not self.max_cp() > limit:
            return float(40)
        for x in range(80, 2, -1):
            x = (x * 0.5)
            if self.calculate_cp(0, 0, 0, x) <= limit:
                return min(x + 1, 40)

    def min_level(self, limit):
        if not self.max_cp() > limit:
            return float(40)
        for x in range(80, 2, -1):
            x = (x * 0.5)
            if self.calculate_cp(15, 15, 15, x) <= limit:
                return max(x - 1, 1)

    def _spreads(self, limit):
        smallest = {"product": 999999999}
        highest = {"product": 0}
        if not limit in self.products:
            self.products[limit] = []

        min_level = self.min_level(limit)
        max_level = self.max_level(limit)

        for level in range(int(min_level * 2), int((max_level + 0.5) * 2)):
            level = str(level / 2).replace('.0', '')

            for stat_product in itertools.product(range(16), range(16), range(16)):
                cp = self.calculate_cp(stat_product[0], stat_product[1], stat_product[2], level)
                if cp > limit:
                    continue

                attack = ((self.atk + stat_product[0]) * (
                    self.cp_multipliers[str(level)]))
                defense = ((self.de + stat_product[1]) * (
                    self.cp_multipliers[str(level)]))
                stamina = floor(((self.sta + stat_product[2]) * (
                    self.cp_multipliers[str(level)])))
                product = (attack * defense * stamina)
                self.products[limit].append(product)
                if product > highest["product"]:
                    highest.update({
                        'product': product,
                        'attack': attack,
                        'defense': defense,
                        'stamina': stamina,
                        'atk': stat_product[0],
                        'de': stat_product[1],
                        'sta': stat_product[2],
                        'cp': cp,
                        'level': level
                    })
                if product < smallest["product"]:
                    smallest.update({
                        'product': product,
                        'attack': attack,
                        'defense': defense,
                        'stamina': stamina,
                        'atk': stat_product[0],
                        'de': stat_product[1],
                        'sta': stat_product[2],
                        'cp': cp,
                        'level': level
                    })
        self.products[limit].sort(reverse=True)
        length = self.ranklength + 1
        del self.products[limit][length:]
        return highest, smallest


class PokemonData(PvpBase):
    def __init__(self, ranklength):
        super(PokemonData, self).__init__()
        self.logger = get_logger(LoggerEnums.plugin)
        self.logger.warning("initializing PokemonData, this will take a while ...")
        self.ranklength = ranklength
        self.data = {}
        self.PokemonId = PokemonId
        self.Form = Form
        gmfile = requests.get("https://raw.githubusercontent.com/pokemongo-dev-contrib/pokemongo-game-master/"
            "master/versions/1595879989869/GAME_MASTER.json")
        templates = gmfile.json()["itemTemplate"]

        i = 0
        for template in templates:
            if (template["templateId"] and template["templateId"].startswith("V") and 
              not template["templateId"].startswith("VS") and
              "POKEMON" in template["templateId"]):
                if i > 0 and i % 50 == 0:
                    self.logger.success("processed {} pokemon templates ...".format(i))
                i += 1
                try:
                    moninfo = template["pokemon"]
                    stats = moninfo["stats"]
                    evolution = []
                    try:
                        for evo in moninfo["evolutionBranch"]:
                            evoId = self.PokemonId[evo["evolution"]].value
                            try:
                                formId = self.Form[evo["form"]].value
                            except:
                                formId = self.Form["{}_NORMAL".format(evo["evolution"])].value
                            evolution.append("{}-{}".format(evoId, formId))
                    except KeyError:
                        evolution = []
                    try:
                        form = self.Form[moninfo["form"]].value
                    except KeyError:
                        # handle Nidoran ...
                        name = moninfo["uniqueId"].replace("_FEMALE", "").replace("_MALE", "")
                        form = self.Form["{}_NORMAL".format(name)].value
                    mon = Pokemon(self.PokemonId[moninfo["uniqueId"]].value,
                            form,
                            stats["baseAttack"],
                            stats["baseDefense"],
                            stats["baseStamina"],
                            evolution,
                            self.ranklength)
                    self.add(mon)
                    self.logger.debug("processed template {}".format(template["templateId"]))
                except Exception as e:
                    self.logger.warning("Exception processing template {}: {} (this is probably ok)".format(
                        template["templateId"], e))
                    continue
            else:
                continue

    def add(self, pokemon: Pokemon):
        self.data[pokemon.ident()] = pokemon

    def __str__(self):
        return str(self.data)

    def getUniqueIdentifier(self, mon, form):
        return "{}-{}".format(mon, form)

    def getPokemonObject(self, mon, form):
        identifier = self.getUniqueIdentifier(mon, form)
        if identifier in self.data:
            return self.data[identifier]
        else:
            return False

    def getAllEvolutions(self, mon, form):
        allEvolutions = []
        try:
            nextEvolution = self.getPokemonObject(mon, form).getEvolution()
        except:
            nextEvolution = False
        while nextEvolution:
            for evolution in nextEvolution:
                allEvolutions.append(evolution)
                furtherEvolutions = self.getAllEvolutions(evolution.split("-")[0], evolution.split("-")[1])
                allEvolutions = allEvolutions + furtherEvolutions
            try:
                nextEvolution = self.data[nextEvolution].getEvolution()
            except:
                nextEvolution = False
        self.logger.debug("found evolutions: {}".format(allEvolutions))
        return allEvolutions

    def getBaseStats(self, mon, form):
        mon = self.getPokemonObject(mon, form)
        stats = {}
        stats["attack"] = mon.atk
        stats["defense"] = mon.de
        stats["stamina"] = mon.sta
        return stats

    def get_pvp_info(self, atk, de, sta, lvl, monster=0, form=0, identifier=None):
        if identifier:
            monster = identifier.split("-")[0]
            form = identifier.split("-")[1]
        elif monster != 0 and form != 0:
            pass
        else:
            return False, False, False, False, False, False, False, False, False, False

        mondata = self.getPokemonObject(monster, form)

        lvl = float(lvl)
        stats_great_product = mondata.greatPerfect["product"]
        stats_ultra_product = mondata.ultraPerfect["product"]

        great_product, great_cp, great_level, great_rank = self.getPokemonObject(monster, form).pokemon_rating(1500, atk, de, sta, lvl)
        great_rating = 100 * (great_product / stats_great_product)
        ultra_product, ultra_cp, ultra_level, ultra_rank = self.getPokemonObject(monster, form).pokemon_rating(2500, atk, de, sta, lvl)
        ultra_rating = 100 * (ultra_product / stats_ultra_product)
        great_id = monster
        ultra_id = monster

        if float(great_level) < lvl:
            great_rating = 0
        if float(ultra_level) < lvl:
            ultra_rating = 0

        return (great_rating, great_id, great_cp, great_level, great_rank,
                ultra_rating, ultra_id, ultra_cp, ultra_level, ultra_rank)

    def getPoraclePvpInfo(self, mon, form, atk, de, sta, lvl):
        if form == 0:
            form = self.Form["{}_NORMAL".format(self.PokemonId(str(mon)).name)].value
        greatPayload = []
        ultraPayload = []
        evolutions = [self.getUniqueIdentifier(mon, form), ] + self.getAllEvolutions(mon, form)

        for evolution in evolutions:
            grating, gid, gcp, glvl, grank, urating, uid, ucp, ulvl, urank = self.get_pvp_info(atk, de, sta, lvl, identifier=evolution)
            if grank < 4096:
                greatPayload.append({
                    'rank' : grank,
                    'percentage': round(grating, 3),
                    'pokemon': evolution.split("-")[0],
                    'form': evolution.split("-")[1],
                    'level': glvl,
                    'cp': gcp
                    })
            if urank < 4096:
                ultraPayload.append({
                    'rank' : urank,
                    'percentage': round(urating, 3),
                    'pokemon': evolution.split("-")[0],
                    'form': evolution.split("-")[1],
                    'level': ulvl,
                    'cp': ucp
                    })
        return greatPayload, ultraPayload


class poraclePvpHelper(mapadroid.utils.pluginBase.Plugin):
    """poraclePvpHelper plugin
    """
    def __init__(self, mad):
        super().__init__(mad)

        self._rootdir = os.path.dirname(os.path.abspath(__file__))
        sys.path.append(self._rootdir)

        self._mad = mad
        self.db = self._mad["db_wrapper"]
        self.logger = get_logger(LoggerEnums.plugin)
        self.wh = self._mad["webhook_worker"]
        
        self.statusname = self._mad["args"].status_name
        self._pluginconfig.read(self._rootdir + "/plugin.ini")
        self._versionconfig.read(self._rootdir + "/version.mpl")
        self.author = self._versionconfig.get("plugin", "author", fallback="unknown")
        self.url = self._versionconfig.get("plugin", "url", fallback="https://www.maddev.eu")
        self.description = self._versionconfig.get("plugin", "description", fallback="unknown")
        self.version = self._versionconfig.get("plugin", "version", fallback="unknown")
        self.pluginname = self._versionconfig.get("plugin", "pluginname", fallback="https://www.maddev.eu")
        self.staticpath = self._rootdir + "/static/"
        self.templatepath = self._rootdir + "/template/"

        # plugin specific
        if self.statusname in self._pluginconfig:
            self.logger.success("found statusname specific config!")
            settings = self.statusname
        else:
            settings = "settings"
        self.target = self._pluginconfig.get(settings, "target", fallback=None)
        self.interval = self._pluginconfig.getint(settings, "interval", fallback=30)
        self.ranklength = self._pluginconfig.getint(settings, "ranklength", fallback=100)


        self._routes = [
            ("/poraclePvpHelper_manual", self.manual),
        ]

        self._hotlink = [
            ("poraclePvpHelper Manual", "poraclePvpHelper_manual", "poraclePvpHelper Manual"),
        ]

        if self._pluginconfig.getboolean("plugin", "active", fallback=False):
            self._plugin = Blueprint(str(self.pluginname), __name__, static_folder=self.staticpath,
                                     template_folder=self.templatepath)

            for route, view_func in self._routes:
                self._plugin.add_url_rule(route, route.replace("/", ""), view_func=view_func)

            for name, link, description in self._hotlink:
                self._mad['madmin'].add_plugin_hotlink(name, self._plugin.name+"."+link.replace("/", ""),
                                                       self.pluginname, self.description, self.author, self.url,
                                                       description, self.version)

    def perform_operation(self):
        # do not change this part ▽▽▽▽▽▽▽▽▽▽▽▽▽▽▽
        if not self._pluginconfig.getboolean("plugin", "active", fallback=False):
            return False
        self._mad['madmin'].register_plugin(self._plugin)
        # do not change this part △△△△△△△△△△△△△△△

        # load your stuff now
        self.logger.success("poraclePvpHelper Plugin starting operations ...")
        poraclePvpHelper = Thread(name="poraclePvpHelper", target=self.poraclePvpHelper,)
        poraclePvpHelper.daemon = True
        poraclePvpHelper.start()

        return True


    def _send_webhook(self, payloads):
        if len(payloads) == 0:
            self.logger.debug2("Payload empty. Skip sending to webhook.")
            return

        # get list of urls
        webhooks = self.target.replace(" ", "").split(",")

        webhook_count = len(webhooks)
        current_wh_num = 1

        for webhook in webhooks:
            payload_to_send = []
            sub_types = "all"
            url = webhook.strip()

            if url.startswith("["):
                end_index = webhook.rindex("]")
                end_index += 1
                sub_types = webhook[:end_index]
                url = url[end_index:]

                for payload in payloads:
                    if payload["type"] in sub_types:
                        payload_to_send.append(payload)
            else:
                payload_to_send = payloads

            if len(payload_to_send) == 0:
                self.logger.debug2("Payload empty. Skip sending to: {} (Filter: {})", url, sub_types)
                continue
            else:
                self.logger.debug2("Sending to webhook url: {} (Filter: {})", url, sub_types)

            payload_list = [payloads, ]

            current_pl_num = 1
            for payload_chunk in payload_list:
                self.logger.debug4("Python data for payload: {}", payload_chunk)
                self.logger.debug4("Payload: {}", json.dumps(payload_chunk))

                try:
                    response = requests.post(
                        url,
                        data=json.dumps(payload_chunk),
                        headers={"Content-Type": "application/json"},
                        timeout=5,
                    )

                    if response.status_code != 200:
                        self.logger.warning("Got status code other than 200 OK from webhook destination: {}",
                                       response.status_code)
                    else:
                        if webhook_count > 1:
                            whcount_text = " [wh {}/{}]".format(current_wh_num, webhook_count)
                        else:
                            whcount_text = ""

                        if len(payload_list) > 1:
                            whchunk_text = " [pl {}/{}]".format(current_pl_num, len(payload_list))
                        else:
                            whchunk_text = ""

                        self.logger.success("Successfully sent payload to webhook{}{}. Stats: {}", whchunk_text,
                                       whcount_text, len(payload_chunk))
                except Exception as e:
                    self.logger.warning("Exception occured while sending webhook: {}", e)

                current_pl_num += 1
            current_wh_num += 1



    def poraclePvpHelper(self):
        self.__last_check = int(time.time())
        if not self.target:
            self.logger.error("no webhook (target) defined in settings - what am I doing here? ;)")
            return False

        try:
            with open("{}/data.pickle".format(self._rootdir), "rb") as datafile:
                data = pickle.load(datafile)
        except Exception as e:
            self.logger.warning("exception trying to load pickle'd data, initializing ... exception: {}".format(e))
            data = None

        if not data:
            data = PokemonData(self.ranklength)
            try:
                with open("{}/data.pickle".format(os.path.dirname(os.path.abspath(__file__))), "wb") as datafile:
                    pickle.dump(data, datafile, -1)
                    self.logger.success("dumped to pickle file")
            except Exception as e:
                self.logger.warning("failed saving to pickle file: {}".format(e))

        self.logger.success("PokemonData object aquired")

        w = 0
        while not self.wh and w < 12:
            w += 1
            self.logger.warning("waiting for the webhook worker to be initialized ... do you have webhooks enabled?")
            time.sleep(10)
        if w > 11:
            self.logger.error("failed trying to access the webhook worker. This plugin needs webhook to be enabled "
                    "in your config file!")
            return False

        while True:
            starttime = int(time.time())
            monsFromDb = self.db.webhook_reader.get_mon_changed_since(self.__last_check)
            payload = self.wh._WebhookWorker__prepare_mon_data(monsFromDb)
            for mon in payload:
                if "individual_attack" in mon["message"]:
                    content = mon["message"]
                    try:
                        form = content["form"]
                    except:
                        form = 0

                    great, ultra = data.getPoraclePvpInfo(content["pokemon_id"], form, content["individual_attack"],
                            content["individual_defense"], content["individual_stamina"], content["pokemon_level"])

                    if len(great) > 0:
                        mon["message"]["pvp_rankings_great_league"] = great
                    if len(ultra) > 0:
                        mon["message"]["pvp_rankings_ultra_league"] = ultra

            self._send_webhook(payload)

            self.__last_check = starttime
            time.sleep(self.interval)


    @auth_required
    def manual(self):
        return render_template("poraclePvpHelper_manual.html",
                               header="poraclePvpHelper manual", title="poraclePvpHelper manual"
                               )

