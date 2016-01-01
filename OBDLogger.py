import time
import obd

#obd.debug.console = True

count = 0
limit = 86400

inputOk = False

#while not inputOk:	
#	cycles = raw_input("\nEnter desired number of log cycles (0 to run indefinitely): ")
#	if cycles.isdigit():
#		if int(cycles) > 0 and int(cycles) < 86400:
#			limit = int(cycles)	
#		inputOk = True
#	else:
#		print "\nPlease enter a valid integer up to 86400 or 0 (zero) to run indefinitely."


print "\nConnecting to OBD Device...\n"

cnx = obd.OBD(fast = False)

cmd = obd.commands.RPM
cmd2 = obd.commands.SPEED

print "\nStarting Logger. Press Ctrl-C to stop.\n"
time.sleep(3)

f = open("data/data_" + time.strftime('%Y%m%d_%H%M%S') + ".txt", "w")
f.write('DATE|TIME|RPM|VEL\n')

try:
	while (count < limit):
		rpm = cnx.query(cmd).value
		vel = cnx.query(cmd2).value
		ts = time.strftime('%d/%m/%Y|%X')
		print 'TimeStamp: ' + str(ts) + ' / RPM: ' + str(rpm) + ' / Vel: ' + str(vel) + ' Km/h'
		f.write(str(ts) + '|' + str(rpm) + '|' + str(vel) + '\n')
		count = count + 1
		time.sleep(.83)
except KeyboardInterrupt:
	pass

cnx.close()
f.close()

print "\n" + str(count) + " records logged succesfully"