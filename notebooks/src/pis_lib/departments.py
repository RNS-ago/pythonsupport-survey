"""DTU's departments by the short names DTU's website gives them: DTU Compute, DTU Electro."""

# By kurser.dtu.dk's department numbers. 13, 24, 33 and 36 have since merged into others; older courses still name them.
BY_NUMBER = {
    "01": "DTU Compute",
    "10": "DTU Physics",
    "12": "DTU Sustain",
    "13": "DTU Transport",
    "22": "DTU Health Tech",
    "23": "DTU Food",
    "24": "DTU Vet",
    "25": "DTU Aqua",
    "26": "DTU Chemistry",
    "27": "DTU Bioengineering",
    "28": "DTU Chemical Engineering",
    "29": "DTU Biosustain",
    "30": "DTU Space",
    "33": "DTU Nanotech",
    "34": "DTU Electro",
    "36": "DTU Bioinformatics",
    "38": "DTU Entrepreneurship",
    "41": "DTU Construct",
    "42": "DTU Management",
    "46": "DTU Wind",
    "47": "DTU Energy",
    "56": "DTU Nanolab",
    "62": "DTU Engineering Technology",
    "88": "Other courses",
}
# The other names sdb.dtu.dk gives them: Danish ones on its Danish pages, and a few long ones.
ALIASES = {
    "DTU Fysik": "DTU Physics",
    "DTU Kemi": "DTU Chemistry",
    "DTU Kemiteknik": "DTU Chemical Engineering",
    "DTU Sundhedsteknologi": "DTU Health Tech",
    "DTU Energi": "DTU Energy",
    "DTU Fødevareinstituttet": "DTU Food",
    "DTU National Food Institute": "DTU Food",
}


def short_name(department):
    """`01 Department of Applied Mathematics and Computer Science`, as courses name it, or sdb.dtu.dk's `DTU Fysik`:
    `DTU Compute`, `DTU Physics`. Any other name stays as it is."""
    return BY_NUMBER.get(department.split(" ", 1)[0]) or ALIASES.get(department, department)
