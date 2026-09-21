"""This file is not split into different modules to make distribution to clients easier."""

import pygame as pg
import asyncio
import json
import math
import logging
import colorsys
import argparse
from enum import Enum
from poker.logger_config import setup_logger
from pathlib import Path

logger = setup_logger(__name__)

pg.init()

CONFIG = {
    "DISPLAY" : {
        "DEF_WIDTH" : 1080,
        "DEF_HEIGHT" : 720
    },
    "PATHS" : {
        "BACKGROUND" : Path("client_assets/background.jpg")
    }
}

class ActivePlayer:
    def __init__(self,player_id,name,chips=0,action=None):
        """Player object used on the client side"""
        self.__id = player_id
        self.__name = name
        self.__player_chips = chips
        self.__action = action
        self.__cards = ["",""]
        self.__chip_change = 0
        self.__player_acting = False
        self.player_pos = []

    def set_name(self,name):
        self.__name = name

    def set_player_chips(self,amount):
        self.__player_chips = amount

    def set_action(self,action):
        self.__action = action

    def get_player_acting(self):
        return self.__player_acting

    def set_player_acting(self,val):
        self.__player_acting = val

    def set_cards(self,cards):
        self.__cards = cards

    def set_chip_change(self,change):
        self.__chip_change = change

    def update(self,data):
        """Updates the chips and last action for the player. Done for each player as this info is displayed."""
        try:
            self.__player_chips = data["chips"]
            self.__action = data["last_action"]
        except KeyError as e:
            raise ValueError(f"Missing field: {e}")

    def draw(self,screen,pos,rad,ended):
        """Draws the player on screen"""
        self.__render_player(screen,pos,rad,ended)
        for position in self.player_pos:
                self.__draw_position(screen,pos,rad,position)

    def __render_player(self,screen,pos,rad,ended):
        """Draws the circle icon for a player around the table. Colour determined by whether or not they are acting currently"""
        pg.draw.circle(screen,(255,0,0) if self.__player_acting else (255,255,255),pos,rad)
        font = pg.font.Font(None,36)
        name_surface = font.render(self.__name,True,(0,0,0))
        name_rect = name_surface.get_rect()
        name_rect.center = (pos[0],pos[1]-0.2*rad)
        screen.blit(name_surface,name_rect)

        chip_surface = font.render(f"{self.__player_chips}",True,(0,0,0))
        chip_rect = chip_surface.get_rect()
        chip_rect.center = (pos[0],pos[1]+0.2*rad)
        screen.blit(chip_surface,chip_rect)

        if not ended:
            self.__render_action(screen,pos,rad)

    def __render_action(self,screen,pos,rad):
        """Draws the text for the last action of a player."""
        font = pg.font.Font(None,36)
        action_surface = font.render(self.__action,True,(0,0,0))
        action_rect = action_surface.get_rect()
        action_rect.center = (pos[0],pos[1]+rad+20)
        screen.blit(action_surface,action_rect)

    def __draw_position(self,screen,pos,rad,position):
        """
        This just draws the "buttons" one might have in a physical game, indicating the SB, BB and D.
        My implementation allows a player to be multiple positions as in a heads-up (1v1) situation.
        The positions of the buttons are calculated as a function of the player's circle's size and position.
        """
        if position == "D":
            centre = (pos[0]+0.7*math.sqrt(2)*rad,pos[1]+0.7*math.sqrt(2)*rad)
        else:
            centre = (pos[0]-0.7*math.sqrt(2)*rad,pos[1]+0.7*math.sqrt(2)*rad) # Will either be SB or BB (or neither) but never both
        pg.draw.circle(screen,(0,0,0),centre,0.4*rad)
        font = pg.font.Font(None,30)
        text_surface = font.render(position,True,(255,255,255))
        text_rect = text_surface.get_rect()
        text_rect.center = centre
        screen.blit(text_surface,text_rect)

    def draw_game_over(self,screen,pos,rad):
        """
        Display information at the end of the game, based upon the game-over message received
        """
        display_cards = self.__cards
        font = pg.font.SysFont("segoeuisymbol",18)
        card_text = f"{display_cards[0]} | {display_cards[1]}"
        cards_surface = font.render(card_text,True,(255,255,255))
        card_rect = cards_surface.get_rect()
        card_rect.center = (pos[0],pos[1]+1.2*rad)
        screen.blit(cards_surface,card_rect)

        if self.__chip_change < 0:
            chip_change_surface = font.render(f"{str(self.__chip_change)}",True,(255,255,255))
        else:
            chip_change_surface = font.render(f"+{str(self.__chip_change)}",True,(255,255,255))

        chip_rect = chip_change_surface.get_rect()
        chip_rect.center = (card_rect.centerx,card_rect.centery+20)
        screen.blit(chip_change_surface,chip_rect)

class PlayerManager:
    def __init__(self):
        """Player manager handles all the updates of all the players in the game."""
        self.players = {}
        self.__active = set()
        self.__active_received = set()

    def __update_player(self,player_id,data):
        """Updates the data of a player based upon the JSON received from the game."""
        try:
            player = self.players[player_id]
            player.__player_chips = data["chips"]
            player.set_name(data["name"])
            player.set_action(data["last_action"])
        except KeyError as e:
            raise ValueError(f"Missing field: {e}")

    def manage_players(self,players):
        """
        Manages the players received in JSON messages from the server
        """
        players_to_pop = []
        for player in self.players:
            if player not in [p["player_id"] for p in players]:
                players_to_pop.append(player)

        for player in players_to_pop:
            self.players.pop(player)

        for player in players:
            self.__handle_player(player["player_id"],player)
            self.__update_player(player["player_id"],player)

        for id in self.__active:
            if id not in self.__active_received:
                self.__active.discard(id)

    def game_over_update(self,data):
        """
        When the "game-over" message is received, it should contain the hands and chip change of all the opponents,
        which can then be displayed to show who profited what and with what cards.
        """
        hands = data["hands"]
        for id,cards in hands.items():
            try:
                self.players[int(id)].set_cards(cards)
            except Exception as e:
                logger.error(f"Error decoding hand: {e}")

        try:
            winners = data["winners"]
            for id,chip_change in winners.items():
                self.players[int(id)].set_chip_change(chip_change)
        except Exception as e:
            logger.error(f"Error decoding winners: {e}")

    def __handle_player(self,player_id,data):
        """This is where we create the new player object and call the update methods."""
        if player_id not in self.__active:
            name = data["name"]
            self.players[player_id] = ActivePlayer(player_id,name)
            self.__active.add(player_id)
            self.__active_received.add(player_id)
        self.players[player_id].update(data)

    def draw_players(self,screen):
        """Draws all the opponents."""
        for player in self.players.values():
            player.draw(screen)

class GameInfo:
    """GameInfo class stores data about the game and the current client."""
    def __init__(self):
        # Player Details
        self.player_obj = None
        self.__name = ""
        self.__ID = -1
        self.__pos = -1
        self.__hand = []
        self.__chips = 0

        # Game Details
        self.__community = []
        self.__total = 0
        self.__min_raise = 0
        self.__order = []

        # Player Manager Object
        self.player_manager = PlayerManager()

        # Attributes Used in Display and Processing
        self.__current_player = None

        self.__game_ended = False

    def get_pos(self):
        return self.__pos

    def get_ID(self):
        return self.__ID

    def get_chips(self):
        return self.__chips

    def get_game_ended(self):
        return self.__game_ended

    def get_hand(self):
        return self.__hand

    def get_order(self):
        return self.__order

    def get_min_raise(self):
        return self.__min_raise

    def get_total(self):
        return self.__total

    def get_community(self):
        return self.__community

    def set_community(self,cards):
        self.__community = cards

    def update_info(self,data):
        """Updates information about the game, based upon the JSON messages"""
        try:
            self.__name = data["name"]
            self.__ID = data["id"]
            self.__chips = data["chips"]
            self.__update_self(data["self"])
            self.players = data["players"]
            self.__order = data["order"]
            self.__pos = data["pos"]
        except KeyError as e:
            raise ValueError(f"Missing field: {e}")

        self.player_manager.manage_players(self.players)

        try:
            self.set_community(data["community"])
            self.__hand = data["hand"]
            self.__total = data["total"]
            self.__min_raise = data["min_raise"]
            self.__current_player = data["current_player"]
            self.__game_ended = data["game_over"]
        except KeyError as e:
            raise ValueError(f"Missing fields: {e}")

        self.__set_positions()
        self.__set_active_player()

    def login_confirm(self,data):
        """When the login confirmation arrives, we make sure the ID is successfully assigned"""
        try:
            self.__ID = data["id"]
            return True
        except KeyError as e:
            logger.error(f"Login confirmation failed: {e}")
            return False

    def __update_self(self,data):
        """Updates the personal information of the player using this client"""
        try:
            player_id = data["player_id"]
            chips = data["chips"]
            name = data["name"]
            last_action = data["last_action"]
            self.__manage_self()
        except KeyError as e:
            raise ValueError(f"Missing field: {e}")

        self.player_obj.set_player_chips(chips)
        self.player_obj.set_action(last_action)

    def __manage_self(self):
        """Ensures that the player has an object for themselves."""
        if not self.player_obj:
            self.player_obj = ActivePlayer(self.__ID,self.__name,chips=self.__chips)

    def __set_positions(self):
        """
        This sets the positions for who is D, SB, and BB.
        It clears the positions beforehand to prevent buildup of incorrect positions.
        It uses the positions of the players within the dealer queue to calculate what position they must be
        """
        for player in self.player_manager.players.values():
            player.player_pos = []

        self.player_obj.player_pos = []

        if self.__order[0] != self.__ID:
            self.player_manager.players[self.__order[0]].player_pos += ["D"]
        elif self.__order[0] == self.__ID:
            self.player_obj.player_pos += ["D"]

        if self.__order[1] != self.__ID:
            self.player_manager.players[self.__order[1]].player_pos += ["SB"]
        elif self.__order[1] == self.__ID:
            self.player_obj.player_pos += ["SB"]

        if self.__order[2%len(self.__order)] != self.__ID:
            self.player_manager.players[self.__order[2%len(self.__order)]].player_pos += ["BB"]
        elif self.__order[2%len(self.__order)] == self.__ID:
            self.player_obj.player_pos += ["BB"]

    def __set_active_player(self):
        """
        Resets everybody to not acting, then sets the correct player to acting.
        This helps with making it clear whose turn it is currently.
        """
        self.player_obj.set_player_acting(False)
        for player in self.__order:
            if player != self.__ID:
                self.player_manager.players[player].set_player_acting(False)

        if self.__current_player == self.__ID:
            self.player_obj.set_player_acting(True)
        else:
            self.player_obj.set_player_acting(False)
            self.player_manager.players[self.__current_player].set_player_acting(True)

    def game_over_update(self,data):
        """Manages the game over update"""
        self.player_obj.set_player_acting(False)
        self.player_manager.game_over_update(data)
        self.__game_ended = True

class UIObject:
    """Base class for my UI components such as buttons and sliders."""
    def __init__(self,size,pos):
        self._rect = pg.Rect(pos[0],pos[1],size[0],size[1])

    def draw(self):
        pass

    def is_clicked(self,pos):
        return self._rect.collidepoint(pos)

class Slider(UIObject):
    """Slider object used for raising, drag and drop along a slider to select a value to raise by."""
    def __init__(self,size,pos,min_value,max_value):
        super().__init__(size,pos)

        # Details about both the slider backdrop, and the slider itself
        self.__min_value = min_value
        self.__max_value = max_value
        self.__value = min_value
        self.__dragging = False
        self.__slider_width = 25
        self.__slider_colour = (255,0,0)
        self.__backdrop_colour = (0,0,0)
        self.__slider_rect = pg.Rect(pos[0],pos[1],self.__slider_width,size[1])

    def set_min_value(self,value):
        if value < 0:
            self.__min_value = 0
        else:
            self.__min_value = value

    def set_max_value(self,value):
        self.__max_value = value

    def set_value(self,value):
        if value < self.__min_value:
            self.__value = self.__min_value
        else:
            self.__value = value

    def get_value(self):
        return self.__value

    def update_slider_position(self):
        """Updates the position of the actual slider based upon the current value."""
        value_range = self.__max_value - self.__min_value
        pos_range = self._rect.width - self.__slider_width
        relative_val = self.__value - self.__min_value
        self.__slider_rect.x = self._rect.x + (relative_val/value_range) * pos_range

    def __calculate_value(self,mouse_x):
        """Calculates the value based upon the position of the slider at that moment in time, using position of the mouse."""
        relative_x = mouse_x - self._rect.x
        value_range = self.__max_value - self.__min_value
        pos_range = self._rect.width - self.__slider_width
        raw_value = (relative_x/pos_range) * value_range + self.__min_value
        rounded_value = round(raw_value / 25) * 25
        return max(self.__min_value, min(self.__max_value, rounded_value))

    def __calculate_colour(self):
        """Uses HSV colours as a nice way to create a smooth rainbow colour gradient as the slider is moved."""
        relative_x = self.__slider_rect.x - self._rect.x
        pos_range = self._rect.width - self.__slider_width
        relative_pos = relative_x / pos_range
        r,g,b = colorsys.hsv_to_rgb(relative_pos,1,1)
        self.__slider_colour = (int(255*r),int(255*g),int(255*b))

    def handle_action(self,event):
        """Handles actions upon the slider such as clicking on the slider, dragging it, or dropping it."""
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            if self.is_clicked(event.pos):
                self.__dragging = True
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
            self.__dragging = False
        elif event.type == pg.MOUSEMOTION and self.__dragging:
            mouse_x = event.pos[0]
            self.__value = int(self.__calculate_value(mouse_x))
            self.update_slider_position()
            self.__calculate_colour()

    def draw(self,screen):
        """Draws the backdrop first, then the slider to go on top of it."""
        pg.draw.rect(screen,self.__backdrop_colour,self._rect)
        pg.draw.rect(screen,self.__slider_colour,self.__slider_rect)

class Button(UIObject):
    """
    Base class for buttons specifically, though it inherits from UIObject overall.
    Lays out some of the basic functionality.
    """
    def __init__(self,size,pos,text):
        super().__init__(size,pos)
        self._text = text
        self._font = pg.font.Font(None,32)

    def get_text(self):
        return self._text

    def draw(self,surface,active=True):
        pg.draw.rect(surface,(0,128,255) if active else (204,229,255),self._rect)
        text_surface = self._font.render(self._text,True,(255,255,255))
        text_rect = text_surface.get_rect()
        text_rect.center = self._rect.center
        surface.blit(text_surface,text_rect)

    def use(self,client):
        """To be overwritten eventually."""
        pass

class SimpleButton(Button):
    """This button is used for almost all buttons, except for the raise button."""
    def __init__(self,size,pos,text):
        super().__init__(size,pos,text)

    def use(self,client):
        asyncio.create_task(client.send_message(client.json_message(self._text)))

class RaiseButton(Button):
    """The raise button changes the state to RAISING when clicked upon, allowing use of the slider."""
    def __init__(self,size,pos):
        super().__init__(size,pos,"RAISE")

    def use(self,client):
        client.set_state(ClientState.RAISING)

class Display:
    """Base class for a display, which is what we see as a user. The inherited classes will be displayed when in certain states."""
    def __init__(self,client):
        self.client = client
        self._buttons = []
        self._HEIGHT,self._WIDTH = self.client.HEIGHT,self.client.WIDTH
        self._BACKGROUND = pg.image.load(CONFIG["PATHS"]["BACKGROUND"])
        self._BACKGROUND = pg.transform.scale(self._BACKGROUND,self.client.DIMENSIONS)

    async def handle_events(self,events):
        for event in events:
            if event.type == pg.QUIT:
                self.client.running = False
            elif event.type == pg.MOUSEBUTTONDOWN:
                await self._handle_button_click(event)
            elif event.type == pg.KEYDOWN:
                self._handle_text_input(event)

    async def _handle_button_click(self):
        pass

    def _draw_buttons(self):
        pass

    def _draw_text(self):
        pass

    def _handle_text_input(self,event):
        """If the event is a text input, this method will handle what to do with it, which is to do with the player input text displayed in the top left."""
        if self.client.inputting_text:
            if event.key == pg.K_RETURN:
                asyncio.create_task(self.client.send_message(self.client.json_message(self.client.input_text)))
                self.client.input_text = "Press TAB to start typing."
                self.client.inputting_text = False
            elif event.key == pg.K_BACKSPACE:
                self.client.input_text = self.client.input_text[:-1]
            elif event.key == pg.K_SPACE:
                self.client.input_text += " "
            else:
                self.client.input_text += event.unicode

        elif event.key == pg.K_TAB:
                self.client.input_text = ""
                self.client.inputting_text = True

    async def render(self):
        pass

    def _render_text(self,screen,text,font,colour,pos,align="centre"):
        """Gives the option to select alignment of the text when rendering."""
        text_surface = font.render(text,True,colour)
        text_rect = text_surface.get_rect()

        if align == "left":
            text_rect.midleft = pos
        elif align == "right":
            text_rect.midright = pos
        else:
            text_rect.center = pos

        screen.blit(text_surface,text_rect)

class LoginScreen(Display):
    """This screen is displayed when users are joining at the start. A very basic interface with only the necessary functionality."""
    def __init__(self,client):
        super().__init__(client)
        # Creating the buttons and spacing them equally in and from the bottom right corner.
        self._buttons = [SimpleButton((self._WIDTH/12,self._HEIGHT/16),(self._WIDTH*0.9-(i)*(20+self._WIDTH/12),self._HEIGHT*0.9),j) for (i,j) in enumerate(["SIGN UP","LOG IN"])]

    async def _handle_button_click(self,event):
        for button in self._buttons:
            if button.is_clicked(event.pos):
                logger.debug(f"BUTTON CLICKED {button.get_text()}")
                if button.get_text() == "LOG IN":
                    asyncio.create_task(self.client.send_message(self.client.json_message("L")))
                elif button.get_text() == "SIGN UP":
                    asyncio.create_task(self.client.send_message(self.client.json_message("S")))

    async def render(self,screen):
        screen.blit(self._BACKGROUND,(0,0))
        self._draw_buttons(screen)
        self._draw_text(screen)

    def _draw_buttons(self,screen):
        for button in self._buttons:
            button.draw(screen)

    def _draw_text(self,screen):
        font = pg.font.Font(None,36)
        self._render_text(screen,self.client.message,font,(255,255,255),(10,15),"left")
        self._render_text(screen,self.client.input_text,font,(255,255,255),(10,50),"left")

class StatsPage(Enum):
    """Used to encode states for the stats page - which stats to request and display"""
    LEADERBOARD = "LEADERBOARD"
    GLOBAL = "GLOBAL"
    PERSONAL = "PERSONAL"

class StatScreen(Display):
    """Page where stats are displayed"""
    def __init__(self,client):
        super().__init__(client)
        # Creating the buttons and spacing them equally in and from the bottom right corner.
        self._buttons = [SimpleButton((self._WIDTH/7,self._HEIGHT/15),(self._WIDTH*0.85-(i)*(20+self._WIDTH/7),self._HEIGHT*0.88),j) for (i,j) in enumerate(["LEADERBOARD","GLOBAL","PERSONAL"])]
        self.__page = StatsPage.PERSONAL

    def _draw_text(self,screen):
        font = pg.font.Font(None,36)
        self._render_text(screen,self.client.message,font,(255,255,255),(10,15),"left")
        self._render_text(screen,self.client.input_text,font,(255,255,255),(10,50),"left")

    def __format_stats(self,stats):
        """When the server sends the stats, they must be properly formatted bfore being displayed"""
        lines = []
        if self.client.stats_type == StatsPage.PERSONAL.value:
            stats = stats[0]
            lines.append("Personal Stats")
            lines.append(f"Username: {stats[0]}")
            lines.append(f"Hands Played: {stats[1]}")
            lines.append(f"Hands Won: {stats[2]}")
            lines.append(f"Win Rate: {stats[3]}%")
            lines.append(f"VPIP: {stats[4]}%")
            lines.append(f"PFR: {stats[5]}%")
            lines.append(f"Aggression: {stats[6]}")
        elif self.client.stats_type == StatsPage.LEADERBOARD.value:
            lines.append("Leaderboard (Top 10)")
            for rank, (username, hands_played, win_rate, total_bb_profit) in enumerate(stats,start=1):
                lines.append(f"{rank}. {username} - Hands Played: {hands_played}, Win Rate: {win_rate}%, Total BB Profit: {total_bb_profit}")
        elif self.client.stats_type == StatsPage.GLOBAL.value:
            stats = stats[0]
            lines.append("Global Stats")
            lines.append(f"Total Games: {stats[0]}")
            lines.append(f"Active Players: {stats[1]}")
            lines.append(f"Average Win Rate: {stats[2]}%")
            lines.append(f"Most Hands Played: {stats[3]}")
        return lines

    async def __request_stats(self):
        """Requests the statistics from the server, based upon the current page state (within the stats page)"""
        parameters = [self.client.game_info.get_ID()] if self.__page == StatsPage.PERSONAL else []
        await self.client.db_request(parameters,self.__page.value)

    def _draw_buttons(self,screen):
        for button in self._buttons:
            button.draw(screen)

    async def render(self,screen):
        """Draws all the components of the display page"""
        screen.blit(self._BACKGROUND,(0,0))
        self._draw_buttons(screen)
        self._draw_text(screen)
        self.__draw_stats(screen)

    def __draw_stats(self,screen):
        """Draws the stats that have been formatted"""
        stats = self.client.stats
        if stats:
            formatted_stats = self.__format_stats(stats)
            font = pg.font.Font(None,36)
            y_offset = 35
            for i,line in enumerate(formatted_stats):
                self._render_text(screen,line.strip(),font,(255,255,255),(100,100+i*y_offset),"left")

    async def _handle_button_click(self,event):
        for button in self._buttons:
            if button.is_clicked(event.pos):

                if button.get_text() == "PERSONAL":
                    self.__page = StatsPage.PERSONAL
                elif button.get_text() == "GLOBAL":
                    self.__page = StatsPage.GLOBAL
                elif button.get_text() == "LEADERBOARD":
                    self.__page = StatsPage.LEADERBOARD
                await self.__request_stats()

class GameScreen(Display):
    """The screen used for most of the game is the Game Screen, which is for when the game is udnerway."""
    def __init__(self,client):
        super().__init__(client)
        self._buttons = [SimpleButton((self._WIDTH/12,self._HEIGHT/16),(self._WIDTH*0.9-(i)*(20+self._WIDTH/12),self._HEIGHT*0.9),j) for (i,j) in enumerate(["FOLD","CHECK","CALL"])]
        self._buttons.append(RaiseButton((self._WIDTH/12,self._HEIGHT/16),(self._WIDTH*0.9-(3)*(20+self._WIDTH/12),self._HEIGHT*0.9)))

    async def _handle_button_click(self,event):
        for button in self._buttons:
            if button.is_clicked(event.pos):
                button.use(self.client)

    async def render(self,screen):
        """The screen has the background, then the user (and their cards), the opponents, the community cards, and some other text."""
        inf = self.client.game_info
        screen.blit(self._BACKGROUND,(0,0))

        ellipse_rect = self._draw_ellipse(screen) # The table has an elliptical shape
        positions = self._generate_positions(len(inf.get_order()),ellipse_rect.center,ellipse_rect.size) # Positions around the elliptical table
        self._draw_opponents(screen,inf,positions,inf.get_game_ended())
        self._draw_self(screen,ellipse_rect,inf)
        self._draw_cards(screen,ellipse_rect,inf)
        self._draw_buttons(screen,inf)
        self._draw_text(screen,ellipse_rect,inf)

    def _draw_self(self,screen,ellipse_rect,inf):
        centre_x,centre_y = ellipse_rect.center
        offset_y = ellipse_rect.size[1] // 2
        position = (centre_x,centre_y+offset_y)
        inf.player_obj.draw(screen,position,self._WIDTH/18,inf.get_game_ended())

    def _draw_text(self,screen,ellipse_rect,inf):
        font = pg.font.Font(None,36)
        if inf.get_total() > 0:
            self._render_text(screen,f"Total: {inf.get_total()}",font,(255,255,255),(ellipse_rect.center[0],ellipse_rect.center[1]+self._HEIGHT/5-20))
        self._render_text(screen,self.client.message,font,(255,255,255),(10,15),"left")
        self._render_text(screen,self.client.input_text,font,(255,255,255),(10,50),"left")

    def _draw_buttons(self,screen,inf):
        for button in self._buttons:
            button.draw(screen,inf.player_obj.get_player_acting())

    def _draw_ellipse(self,screen):
        ellipse_rect = pg.Rect(0,0,0.75*self._WIDTH,0.625*self._HEIGHT)
        ellipse_rect.center = (0.5*self._WIDTH,(7/16)*self._HEIGHT)
        pg.draw.ellipse(screen,(0,150,0),ellipse_rect)
        return ellipse_rect

    def _draw_cards(self,screen,ellipse_rect,inf):
        """Draws the user's cards and the community cards."""
        for i,card in enumerate(inf.get_hand()):
            card_image = pg.image.load(Path(f"./client_assets/svg_playing_cards/fronts/{card['suit']}_{card['rank']}.svg"))
            card_image = pg.transform.scale(card_image,(self._WIDTH/12,self._HEIGHT/5))
            card_rect = card_image.get_rect()
            card_width,card_height = card_rect.width,card_rect.height
            card_rect.center = (self._WIDTH/8+(-0.5+2*i)*(10+card_width/2),self._HEIGHT*7/8)
            screen.blit(card_image, card_rect)

        for i,card in enumerate(inf.get_community()):
            card_image = pg.image.load(Path(f"./client_assets/svg_playing_cards/fronts/{card['suit']}_{card['rank']}.svg"))
            card_image = pg.transform.scale(card_image,(self._WIDTH/14,self._HEIGHT*2/11))
            card_rect = card_image.get_rect()
            card_width,card_height = card_rect.width,card_rect.height
            card_rect.center = (ellipse_rect.center[0]+(-2+i)*(card_width+10),ellipse_rect.center[1])
            screen.blit(card_image, card_rect)

    def _generate_positions(self, num, pos, dimensions,exclusion=math.pi/3):
        """Generates the positions for opponents to be displayed, using the parametric equation for an ellipse."""
        centre_x = pos[0]
        centre_y = pos[1]
        a, b = dimensions[0] // 2, dimensions[1] // 2
        available = 2*math.pi-exclusion # Reserves part of the ellipse for the user's player to be drawn (directly at the bottom)
        positions = []

        for i in range(num):
            t = i * available / num  + 2.15*exclusion
            t = math.pow(t / (2*math.pi),0.8) * 2 * math.pi
            x = centre_x + a * math.cos(t)
            y = centre_y + b * math.sin(t)
            positions.append((int(x), int(y)))

        return positions

    def _draw_opponents(self,screen,inf,pos,ended):
        """Using the generated positions around the ellipse, draws the positions of each opponent"""
        if inf.get_order():
            positions = pos
            k = 0
            for i in range(inf.get_pos()+1,inf.get_pos()+len(inf.get_order())):
                j = i%len(inf.get_order())
                id = inf.get_order()[j]

                inf.player_manager.players[id].draw(screen,positions[k],self._WIDTH/18,ended)
                if ended:
                    inf.player_manager.players[id].draw_game_over(screen,positions[k],self._WIDTH/18)

                k += 1

class RaisingScreen(GameScreen):
    """Inheriting from the Game Screen, the raising screen is used when raising, though the majority of the layout is the same."""
    def __init__(self, client):
        super().__init__(client)
        self.__min_raise = self.client.game_info.get_min_raise()
        self.__max_raise = self.client.game_info.get_chips()
        self._buttons = [SimpleButton((self._WIDTH/12,self._HEIGHT/16),(self._WIDTH*0.9-(i)*(20+self._WIDTH/12),self._HEIGHT*0.9),j) for (i,j) in enumerate(["CONFIRM","CANCEL"])] #Add buttons
        self.slider = Slider((self._WIDTH*0.4,self._HEIGHT*0.075),(self._WIDTH*0.35,self._HEIGHT*0.85),self.__min_raise,self.__max_raise)

    async def handle_events(self,events):
        """Event handling largely the same, but must also handle interaction with the slider object."""
        await super().handle_events(events)
        for event in events:
            self.slider.handle_action(event)

    async def _handle_button_click(self,event):
        for button in self._buttons:
            if button.is_clicked(event.pos):
                if button.get_text() == "CANCEL":
                    self.client.set_state(ClientState.PLAYING)
                elif button.get_text() == "CONFIRM":
                    asyncio.create_task(self.client.send_message(self.client.json_message(f"raise {self.slider.get_value()}")))
                    self.client.set_state(ClientState.PLAYING)

    def __validate_input_raise(self):
        """Checks the input raise to make sure it is valid - enforces the limits."""
        if self.client.input_text.strip().isnumeric():
            raise_amount = int(self.client.input_text)
            self.slider.set_value(max(self.__min_raise,min(self.__max_raise,raise_amount)))
            self.slider.update_slider_position()

    def _handle_text_input(self,event):
        """Where in the other screens, the input text will typically be sent to the game/server, here it is used to set the raise value"""
        if self.client.inputting_text:
            if event.key == pg.K_RETURN:
                self.__validate_input_raise()
                self.client.input_text = "Press TAB to start typing."
                self.client.inputting_text = False
            elif event.key == pg.K_BACKSPACE:
                self.client.input_text = self.client.input_text[:-1]
            elif event.key == pg.K_SPACE:
                self.client.input_text += " "
            else:
                self.client.input_text += event.unicode

        elif event.key == pg.K_TAB:
                self.client.input_text = ""
                self.client.inputting_text = True

    async def render(self,screen):
        """Also similar rendering, but here accounts for the slider"""
        await super().render(screen)
        self.slider.draw(screen)

        font = pg.font.Font(None,36)
        self._render_text(screen, f"Raise Amount: {self.slider.get_value()}",font,(255,255,255),(self._WIDTH*0.5,self._HEIGHT*0.92))

class GameOverScreen(GameScreen):
    """Once again, inheriting from Game Screen, this screen is very similar to the game screen."""
    def __init__(self,client):
        super().__init__(client)
        self._buttons = [SimpleButton((self._WIDTH/12,self._HEIGHT/16),(self._WIDTH*0.9-(i)*(20+self._WIDTH/12),self._HEIGHT*0.9),j) for (i,j) in enumerate(["PLAY"])]

    async def _handle_button_click(self, event):
        for button in self._buttons:
            if button.is_clicked(event.pos):
                if button.get_text() == "QUIT":
                    await self.client.send_message(self.client.json_message("quit"))
                elif button.get_text() == "PLAY":
                    await self.client.send_message(self.client.json_message("play"))

class ClientState(Enum):
    """Encodes the current state of the client, which determines what is displayed for the client and how their actions are handled"""
    JOINING = "JOINING"
    STATS = "STATS"
    PLAYING = "PLAYING"
    RAISING = "RAISING"
    ENDED ="ENDED"

class Client:
    """The client is what the user sees and interacts with to play the game"""
    def __init__(self,width=1080,height=720):
        # Info about the game and the user
        self.game_info = GameInfo()
        self.stats = ""
        self.stats_type = None

        # Some display parameters
        self.WIDTH = width
        self.HEIGHT = height
        self.DIMENSIONS = (width,height)
        self.ASPECT_RATIO = self.WIDTH/self.HEIGHT

        self.message = "Connecting"
        self.input_text = "Press TAB to start typing."
        self.inputting_text = False

        self.__state = ClientState.JOINING

        # Stores the states so that the display can be changes easily
        self.__screens = {
            ClientState.JOINING:LoginScreen(self),
            ClientState.STATS:StatScreen(self),
            ClientState.PLAYING:GameScreen(self),
            ClientState.RAISING:RaisingScreen(self),
            ClientState.ENDED:GameOverScreen(self)
        }

        # Reader and writer to communicate with the server
        self.__reader = None
        self.__writer = None

    async def __open_connection(self,ip):
        """Opens the connection to the server, specifying the IP and the port."""
        try:
            self.__reader,self.__writer = await asyncio.open_connection(ip,5001)
            self.message = "Connected!!"
        except Exception as e:
            self.message = f"Failed to connect: {str(e)}"
            raise

    def set_state(self,state):
        """Sets the value of the client state"""
        if state in self.__screens:
            self.__state = state
            if state == ClientState.RAISING:
                self.__update_raise_state()

    async def db_request(self,params,type):
        """Requests database information from the server"""
        await self.send_message(self.__json_query(params,type))

    def __update_raise_state(self):
        self.__screens[self.__state].raise_amount = self.game_info.get_min_raise()
        self.__screens[self.__state].max_raise = self.game_info.get_chips()
        self.__screens[self.__state].slider.set_min_value(self.game_info.get_min_raise())
        self.__screens[self.__state].slider.set_max_value(self.game_info.get_chips()+self.game_info.get_total())
        self.__screens[self.__state].slider.set_value(self.game_info.get_min_raise())
        self.__screens[self.__state].slider.update_slider_position()

    def json_message(self,message):
        """Formatting messages to be sent as JSON messages."""
        return {"type":"input",
                "message":message}

    def __json_query(self,params,type):
        """Formatting queries to be sent as JSON messages."""
        return {"type":"query",
                "params":params,
                "req":str(type)}

    async def __handle_events(self):
        """Events are handled dependent on the current state."""
        events = pg.event.get()
        await self.__screens[self.__state].handle_events(events)

    async def __render(self,screen):
        """Renders the display based upon current state"""
        await self.__screens[self.__state].render(screen)

    async def send_message(self,message):
        """Sending messages to the server."""
        try:
            logger.debug(f"SENT {message}")
            message = json.dumps(message)
            self.__writer.write(f"{message}\n".encode())
            await self.__writer.drain()
        except Exception as e:
            logger.error(f"Error sending data: {e}")

    def __decode_message(self,message):
        """The "type" field can provide info to change the state or inform how to process the data."""
        try:
            data = json.loads(message)
            if data.get("type","none") == "login-confirm":
                success = self.game_info.login_confirm(data)
                if success:
                    self.set_state(ClientState.STATS)
            elif data.get("type","none") == "game-state":
                self.game_info.update_info(data)
                self.set_state(ClientState.PLAYING)
            elif data.get("type","none") == "message-state":
                self.message = data["message"]
            elif data.get("type","none") == "game-over":
                self.game_info.game_over_update(data)
                self.set_state(ClientState.ENDED)
            elif data.get("type","none") == "query-result":
                self.stats = data["result"]
                self.stats_type = data["req"]
            else:
                pass
        except Exception as e:
            logger.error(f"Error decoding message: {e}")

    async def __receive_message(self):
        """Continuously runs to wait for incoming messages and begin their processing."""
        while self.running:
            try:
                data = await self.__reader.readline()
                if data:
                    message = data.decode().strip()
                    logger.debug(f"MESSAGE: {message}")
                    self.__decode_message(message)
                else:
                    break
            except Exception as e:
                logger.error(f"Error receiving data: {e}")
                self.running = False
                break

    async def run(self,ip):
        """
        This method is ultimately what runs the client. It runs continously in the background,
        coordinating event handling and rendering.
        """
        try:
            pg.init()
            screen = pg.display.set_mode(self.DIMENSIONS)
            pg.display.set_caption("Poker Client")

            self.running = True

            await self.__open_connection(ip)
            task = asyncio.create_task(self.__receive_message())

            while self.running:
                await self.__handle_events()
                await self.__render(screen)
                pg.display.flip()
                await asyncio.sleep(0.01)

            if self.__writer:
                self.__writer.close()
                await self.__writer.wait_closed()

            task.cancel()

        except Exception as e:
            logger.debug(f"An exception occurred: {e}")
        finally:
            pg.quit()

async def main(args):
    """This just initialises the client object and calls the run method."""
    client = Client(CONFIG["DISPLAY"]["DEF_WIDTH"],CONFIG["DISPLAY"]["DEF_HEIGHT"])
    await client.run(args.ip)

if __name__ == "__main__":
    """
    Argparse is what I will use to allow for different devices to join as obviously
    the server IP must be entered somewhere.
    """
    parser = argparse.ArgumentParser(description="NEA Poker Client")
    parser.add_argument('--ip',type=str,default="127.0.0.1", help="The IP address or hostnameof the server")
    parser.add_argument('--debug', action='store_true', help="Enable debug logging")
    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    asyncio.run(main(args),debug=args.debug)