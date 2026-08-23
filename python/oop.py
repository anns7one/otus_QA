class Regtangle:
    def __init__(self, width, height):
        self.width = width
        self.height = height
    
    @property
    def area(self):
        return self.width * self.height
    
    @property
    def perimeter(self):
        return 2 * (self.width + self.height)
    
    @property
    def __str__(self):
        return f'Rectangle(width={self.width}, height={self.height})'
    
r = Regtangle(5, 10)
print(r.perimeter)