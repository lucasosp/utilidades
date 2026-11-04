import sys

if "--acceso-directo" in sys.argv:
    from .windows import crear_accesos_directos

    for ruta in crear_accesos_directos():
        print(f"  Creado: {ruta}")
else:
    from .app import main

    main()
