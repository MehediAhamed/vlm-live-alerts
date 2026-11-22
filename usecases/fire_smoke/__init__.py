from ..base import UseCase


class FireSmoke(UseCase):
    name = "Fire and Smoke Warning"
    description = "Spots smoke or flames early and raises an instant danger alert."
    prompt = ("You are a fire safety camera. Look for any visible flames, fire, sparks or smoke. "
              "If you see any, reply exactly 'ALERT: <fire or smoke, and where>'. Otherwise reply exactly 'CLEAR'.")
    hits_needed = 1
    cooldown = 10


USECASE = FireSmoke()
