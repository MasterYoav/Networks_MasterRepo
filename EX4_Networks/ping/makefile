ping: ping.o
	gcc -o ping ping.o

ping.o: ping.c ping.h
	gcc -c ping.c -o ping.o

clean:
	rm -f *.o ping